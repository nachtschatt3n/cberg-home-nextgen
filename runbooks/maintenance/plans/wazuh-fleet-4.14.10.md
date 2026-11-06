---
plan_id: wazuh-fleet-4.14.10
component: wazuh
also_covers:                          # every image PR #491 moves; coverage.py matches members on these
  - wazuh-indexer
  - wazuh-manager-master
  - wazuh-dashboard
  - wazuh-agent                       # DaemonSet image wazuh/wazuh-agent, also 4.14.9 -> 4.14.10 in #491.
                                      # There is NO wazuh-manager-worker in this cluster (single-node manager).
pr: 491                               # Renovate "fix(container): update wazuh group ( 4.14.9 -> 4.14.10 )",
                                      # 4 files, CI green (Flate Render Gate + Flux Local Diff), 2026-11-06.
                                      # NOT merged as a unit: §3 lands it in three ordered commits.
kind: image
current: "4.14.9"                     # live 2026-11-06 on all four workloads (pod imageIDs in §5.1)
target: "4.14.10"
update_type: security
risk: medium                          # patch line, but it restarts the whole SIEM pipeline and 4.14.10 changes
                                      # how the agent's logcollector opens files (symlink vetting, §1.3), which
                                      # is exactly how every container log reaches Wazuh here.
est_duration_min: 55                  # 10 pre-checks + 10 stage A + 10 stage B + 10 stage C + 15 ingestion gate
needs_reboot: false
touches:
  namespaces: [security]
  resources:
    - statefulset/wazuh-indexer                    # pod wazuh-indexer-0 recreated (single node, ~2 min SIEM write outage)
    - pvc/wazuh-indexer-data-wazuh-indexer-0       # RWO Longhorn, re-attached; OpenSearch 2.19.6 on both sides
    - statefulset/wazuh-manager-master             # pod wazuh-manager-master-0 recreated
    - pvc/wazuh-manager-master-wazuh-manager-master-0  # RWO Longhorn: /var/ossec/{etc,queue,logs}, /etc/filebeat
    - deployment/wazuh-dashboard
    - daemonset/wazuh-agent                        # 3 pods, maxUnavailable 1
    - configmap/unifi-decoder                      # NOT edited; reloaded by analysisd at manager start
    - configmap/envoy-decoder                      # NOT edited; reloaded
    - configmap/wazuh-local-rules                  # NOT edited; reloaded
    - httproute/wazuh-dashboard                    # NOT edited; backend absent ~1-2 min
  shared:
    - siem/wazuh                      # all security alerting (sweep security-check slice 4, Falco->Wazuh path)
    - falco-event-path                # falco.log is shipped only by the wazuh agents
    - monitoring                      # §4 reads the wazuh-alerts PrometheusRule alerts
depends_on: []
conflicts_with:
  - flux-oci-chart-sources            # its stage 3 restarts DaemonSet security/falco: the Falco feed is one of
                                      # the two ingestion controls in §4.4, so a same-window falco roll makes a
                                      # pass/fail there unattributable. Both plans touch ns security.
  - longhorn-1.13.0                   # engine upgrade while both wazuh RWO volumes detach/re-attach
  - talos-linux-1.14.5                # node rolls restart every wazuh pod; never stack on a SIEM version change
exclusive: false
security_ref: F-68eb92c1              # see also F-97ef819c, F-169ac031 (detail on the DB records only)
capability_change: false             # a fix/hardening patch: no new feature, route, permission or exposure.
                                      # Upstream behaviour changes are fixes (logcollector refuses untrusted
                                      # symlinks/non-regular files; RBAC MATCH fixes; rule-tree WARNING with the
                                      # hard limit disabled by default). §4 proves our feeds are unaffected.
rollback_class: git-revert            # indexer: version-string-only diff, same OpenSearch 2.19.6 => same on-disk
                                      # format; manager: no wazuh-db schema files changed 4.14.9..4.14.10 (§1.2).
                                      # Longhorn nightly backups of both PVCs are the safety net, not the path.
finding_refs:                         # queried 2026-11-06 with SWEEP_PG_DSN up (`finding list --grep wazuh`)
  - F-68eb92c1                        # security: wazuh-manager 4.14.9 image finding (newer tag available)
  - F-97ef819c                        # security: wazuh-indexer 4.14.9 image finding
  - F-169ac031                        # security: wazuh-dashboard 4.14.9 image finding
  - F-25bc9743                        # version: wazuh-manager-master 4.14.9 -> 4.14.10
  - F-c42da5d5                        # version: wazuh-indexer 4.14.9 -> 4.14.10
  - F-7044093c                        # version: wazuh-dashboard 4.14.9 -> 4.14.10
  - F-a138b984                        # version: wazuh-agent 4.14.9 -> 4.14.10
                                      # NOT claimed: F-045b617d (AR-029, no upstream fix), AR-023 root/privileged rows.
review: null
status: draft
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/wazuh-siem-recovery.md
  - docs/sops/longhorn.md
  - docs/sops/backup.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-11-06"
premises:
  - id: live-indexer-4.14.9
    why: "§3 stage A edits exactly this pin. A different live image means Step 0 or a manual merge of #491 already moved it."
    run: kubectl get sts wazuh-indexer -n security -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "wazuh/wazuh-indexer:4.14.9"
  - id: live-manager-4.14.9
    why: "§3 stage B; same reason."
    run: kubectl get sts wazuh-manager-master -n security -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "wazuh/wazuh-manager:4.14.9"
  - id: live-dashboard-4.14.9
    why: "§3 stage C; same reason."
    run: kubectl get deploy wazuh-dashboard -n security -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "wazuh/wazuh-dashboard:4.14.9"
  - id: live-agent-4.14.9
    why: "§3 stage C; same reason."
    run: kubectl get ds wazuh-agent -n security -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "wazuh/wazuh-agent:4.14.9"
  - id: wazuh-ks-ready
    why: "Never stack a version change on a failing Kustomization (it lives in ns security, not flux-system)."
    run: kubectl get kustomization wazuh -n security -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: indexer-path-data-on-pvc
    why: "Data safety of stage A rests on this: without path.data on the PVC, an indexer pod restart wipes every index (incident 2026-07-12, wazuh-siem-recovery.md)."
    run: "kubectl get configmap wazuh-indexer-config -n security -o jsonpath='{.data.opensearch\\.yml}' | grep -c '^path.data: /var/lib/wazuh-indexer'"
    expect_exact: "1"
  - id: custom-rule-ids-unique
    why: "analysisd refuses duplicate rule IDs at start; the manager restart in stage B re-reads all three custom rule ConfigMaps (unifi 50, envoy 9, local 5 rules on 2026-11-06)."
    run: cat kubernetes/apps/security/wazuh/app/unifi-decoder-configmap.yaml kubernetes/apps/security/wazuh/app/envoy-decoder-configmap.yaml kubernetes/apps/security/wazuh/app/wazuh-local-rules-configmap.yaml | grep -o 'rule id="[0-9]*"' | sort | uniq -d | wc -l
    expect_exact: "0"
  - id: manager-mounts-custom-rules
    why: "§4.3 asserts the UniFi/Falco rules load after the roll; that only means something if the manager still mounts the three ConfigMaps."
    run: kubectl get sts wazuh-manager-master -n security -o jsonpath='{.spec.template.spec.volumes[*].configMap.name}'
    expect_contains: "unifi-decoder unifi-decoder envoy-decoder envoy-decoder wazuh-local-rules"
  - id: agent-ds-maxunavailable-1
    why: "Stage C relies on one node at a time so two nodes keep shipping while the third rolls."
    run: kubectl get ds wazuh-agent -n security -o jsonpath='{.spec.updateStrategy.rollingUpdate.maxUnavailable}'
    expect_exact: "1"
---

# wazuh fleet — 4.14.9 → 4.14.10 (indexer, manager, dashboard, agent)

## 1) Summary & why held

### 1.1 What changes and why it was held

Renovate's grouped PR #491 moves all four Wazuh images in
`kubernetes/apps/security/wazuh/app/` from `4.14.9` to `4.14.10`. These images
are `wazuh/wazuh-indexer`, `wazuh/wazuh-manager`, `wazuh/wazuh-dashboard` and
`wazuh/wazuh-agent`. The indexer's two `busybox:1.38.0` init containers do not
change. There is no worker manager.

The update is security-driven. Open sweep findings exist on the current
manager, indexer and dashboard tags (`security_ref` above). The detail stays
on the DB records.

**Why it was held.** The hold came from G3: the auto-updater could not verify
the release notes. That is a real upstream state, not a tooling bug. On
2026-11-06 `wazuh/wazuh` has a **`v4.14.10` git tag but no GitHub Release
object**. `gh release list` shows only `Wazuh v4.14.10 RC 1` and `RC 2` as
pre-releases, and `v4.14.9` is still marked "Latest". The tag commit
(`6e7835b4`, 2026-10-28) is the RC2 commit. The final Docker Hub tags were
pushed on 2026-11-05 between 15:38Z and 15:45Z. The notes are in
`CHANGELOG.md` at the `v4.14.10` tag. Auto-update also cannot apply a
multi-package PR. Holding this patch was correct: it restarts the whole SIEM,
and one upstream change (§1.3) touches the exact mechanism our container-log
collection depends on.

### 1.2 Upstream evidence (read at the tags, 2026-11-06)

- **wazuh-indexer** (`wazuh/wazuh-indexer` compare `v4.14.9...v4.14.10`): 11
  commits. They touch only `VERSION.json`, packaging scripts, a workflow, the
  security-lake integration README/lambda and an empty CHANGELOG section. The
  live node reports OpenSearch `2.19.6` with plugins `2.19.6.0`. **The
  OpenSearch version does not change, so the on-disk index format does not
  change.** That makes a downgrade safe on the same data dir.
- **wazuh-dashboard / plugins** CHANGELOG at v4.14.10: "Support for Wazuh
  4.14.10", plus one fix to the active-response location shown in
  Server management. It stays on OpenSearch Dashboards 2.19.6 rev 02.
- **wazuh-docker** v4.14.10: changes only the image build path (build from the
  production repo, certs-generator image `0.0.5`). The `check_repository.sh`
  and `filebeat_module.sh` diffs are build-time only. There is no
  entrypoint/config change for our manifests.
- **wazuh (manager + agent)** CHANGELOG `[v4.14.10]`: about 50 fixes, most of
  them security hardening (path traversal, bounds checks, RBAC `run_as`/`MATCH`
  fixes). It has **no wazuh-db schema files**: the compare diff contains no
  `schema*`/`*.sql` path. The items that matter here:
  - Manager, Added: *"rule tree memory thresholds to `wazuh-analysisd` to warn
    about and reject rulesets whose rule tree grows too large."* The defaults
    in `etc/internal_options.conf@v4.14.10` are
    `analysisd.rule_tree_memory_warning=25%` and
    **`analysisd.rule_tree_memory_limit=0`** ("0 disables it"). The reject path
    (`(5108) ... Ruleset loading aborted`) is therefore **off by default**. At
    most we get a `(7621)` warning. §4.3 greps for both codes.
  - Agent, Fixed (#39649): *"Fixed logcollector following symbolic links and
    opening non-regular files without validating them on Linux and macOS."*
    See §1.3.
  - Agent, Changed (#40477): logcollector ignores sockets pushed in centralized
    config unless `logcollector.remote_commands` is set. We push no socket
    targets, so this does not apply.

### 1.3 The real gotcha: logcollector symlink vetting vs our container-log tail

Our agent `<localfile>` tails `/host/var/log/containers/*.log`. **Every one of
those entries is a symlink** to `/var/log/pods/<ns>_<pod>_<uid>/<c>/0.log`. The
symlink resolves through the agent's `/var/log` hostPath mount. This path
produces the envoy-access-log rules (`1007xx`), about 186 of the last 6 h of
alerts.

PR #39649 replaces the plain `wfopen()` with `w_fopen_vetted_follow()`. The PR
body says it walks the path one component at a time and accepts:

> a regular file [...] **Symlinks:** every symlink followed must be owned by
> root, sit in a directory only root can write to, or be owned by the owner of
> the final file. **Hard links:** an entry with more than one hard link [...]
> is accepted only in a directory owned by root or by the entry's owner that
> is not writable by group or others.

A rejected file is logged once as
`mwarn(FOPEN_ERROR ...)` = `(1103): Could not open file '<f>' due to [(<errno>)-(<msg>)]`
(`src/error_messages/error_messages.h@v4.14.10`), with errno `EPERM`/`EINVAL`.
After that the file is **silently not read**.

Measured live on 2026-11-06 (`wazuh-agent-6mw7m`):
- the symlinks are `root root lrwxrwxrwx`;
- `/host/var/log/containers`, `/var/log`, `/var/log/pods/*` and the per-container
  dirs are `root root drwxr-xr-x`;
- `0.log` is `root root -rw-r-----` with link count 1;
- `/var/run/falco/falco.log` is a regular `root root` file;
- logcollector runs as root.

On paper every path passes the new checks. This is still the single biggest
regression risk, so §4.5 measures it directly: zero `(1103)` lines on the new
agents, and container-log alerts must arrive after the roll. The baseline
count of `(1103)` lines on the current agent is `0`.

### 1.4 Ordering (version skew)

Wazuh's upgrade order is indexer → manager → dashboard → agents. An agent must
never be newer than its manager, and the dashboard plugin must match the
manager API. All four sit in one Flux Kustomization (`security/wazuh`), so
merging #491 as-is would roll all four at once. Then a failure could not be
attributed, and the manager's filebeat could start against a restarting
indexer. §3 therefore lands three ordered commits on `main` with a health
gate between them, then closes #491.

## 2) Pre-checks

Run from the repo root on the Mac mini. Set the window start marker first:

```bash
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 runbooks/plan-premises.py wazuh-fleet-4.14.10 --require-premises   # all PASS, no REFUSED
T0_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo "T0=$T0_UTC"
```

2.1 **Upstream state unchanged.** The final tags must still be the digests the
plan was written against. A re-push means re-review.
```bash
for i in wazuh-manager wazuh-indexer wazuh-dashboard wazuh-agent; do
  curl -s "https://hub.docker.com/v2/repositories/wazuh/$i/tags/4.14.10" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('$i', d.get('digest'))"; done
```
Expected (2026-11-06):
- manager `sha256:dcda4869e2f792e92f03bce93f85b4bdf103756ea61cfca8ba9f3eabeb05365b`
- indexer `sha256:e56f85ed9e79f113c0f2d2a7965171cd8e063262ec88e110086acdb1f69f2240`
- dashboard `sha256:0eebab19802342b841a258f56d6fa0fb085cdae08ab5eb2e45f9455c906d719a`
- agent `sha256:c30f8cdf7e535674c9f9881aa2824e5e94f7e3f66dd2b90eaf36c4ad155c6526`

A `None` or a different digest means STOP and re-plan. Also run
`gh release list -R wazuh/wazuh -L 5`. If a `v4.14.10` GA release now exists,
read its body for anything absent from the tag CHANGELOG.

2.2 **Indexer health baseline. This gate must PASS before stage A.**
```bash
kubectl exec -n security wazuh-manager-master-0 -c wazuh-manager -- sh -c '
U="$INDEXER_USERNAME:$INDEXER_PASSWORD"; B=https://wazuh-indexer:9200
curl -s -k -u "$U" "$B/_cluster/health" | python3 -c "import sys,json; d=json.load(sys.stdin); print(\"STATUS\",d[\"status\"],\"UNASSIGNED\",d[\"unassigned_shards\"])"
echo NONGREEN=$(curl -s -k -u "$U" "$B/_cat/indices?h=health" | grep -v -c green)
echo INDICES=$(curl -s -k -u "$U" "$B/_cat/indices?h=index" | wc -l)
echo ALERTDOCS=$(curl -s -k -u "$U" "$B/_cat/count/wazuh-alerts-*?h=count")
curl -s -k -u "$U" -o /dev/null -w "PIPELINE=%{http_code}\n" "$B/_ingest/pipeline/filebeat-7.10.2-wazuh-alerts-pipeline"
curl -s -k -u "$U" -o /dev/null -w "TEMPLATE=%{http_code}\n" "$B/_template/wazuh"'
```
PASS: `STATUS green UNASSIGNED 0`, `NONGREEN=0`, `PIPELINE=200`, `TEMPLATE=200`.
Record `INDICES` and `ALERTDOCS` as the baselines (2026-11-06: 133 indices,
682 211 alert docs). A `yellow`/`red` status, or a 404 on the pipeline, means
a pre-existing fault: STOP and fix it per `wazuh-siem-recovery.md` first.

2.3 **Backups fresh** (the data-safety net for both RWO volumes):
```bash
kubectl get volumes -n storage pvc-13694b98-5c6d-4fb5-b3a7-cb9837e2cabb pvc-a7b0cc31-d06f-455d-a0bd-c869b7e79eab \
  -o custom-columns='NAME:.metadata.name,ROB:.status.robustness,LAST:.status.lastBackupAt'
kubectl get cronjob -n storage daily-backup-all-volumes -o jsonpath='{.status.lastSuccessfulTime}{"\n"}'
```
PASS: both volumes are `healthy`, and `LAST` falls within the last 26 h (the
CronJob runs at 23:00 UTC). Write down the newest indexer backup name for §5.3:
`kubectl get backups.longhorn.io -n storage -l backup-volume=pvc-13694b98-5c6d-4fb5-b3a7-cb9837e2cabb --sort-by=.status.backupCreatedAt -o name | tail -1`.

2.4 **UniFi sample for the §4.3 ruleset test.** Save the newest real UniFi
console line. It lives only in `/tmp` on the Mac, is never committed, and is
deleted at the end.
```bash
kubectl exec -n security wazuh-manager-master-0 -c wazuh-manager -- sh -c '
U="$INDEXER_USERNAME:$INDEXER_PASSWORD"; B=https://wazuh-indexer:9200
curl -s -k -u "$U" -H "Content-Type: application/json" "$B/wazuh-alerts-*/_search" \
 -d "{\"size\":1,\"sort\":[{\"@timestamp\":\"desc\"}],\"_source\":[\"full_log\"],\"query\":{\"term\":{\"rule.id\":\"100103\"}}}"' \
 | python3 -c "import sys,json; print(json.load(sys.stdin)['hits']['hits'][0]['_source']['full_log'])" > /tmp/wz-unifi-sample.log
kubectl exec -i -n security wazuh-manager-master-0 -c wazuh-manager -- /var/ossec/bin/wazuh-logtest < /tmp/wz-unifi-sample.log | grep -i -E "id: '100103'|alert to be generated"
```
PASS (baseline, measured 2026-11-06): `id: '100103'` and `**Alert to be generated.`
If no 100103 hit exists, the UniFi console feed has been silent. Rule 100103
fired 6 times in the 14 days before 2026-11-06, last on 2026-11-05. In that
case use any `rule.id` between 100102 and 100199 that has a hit, and expect
that id.

2.5 **No in-flight change.** `flux get kustomizations -A | awk 'NR==1 || $5 != "True"'`
must show nothing for `security`. `kubectl get pods -n security | grep wazuh`
must show 6 pods `Running`, 1/1.

2.6 **Manager daemon baseline** for §4.2. `wazuh-control status` exits 1 even
when it is healthy (measured 2026-11-06), so read the count, not the exit
code:
`kubectl exec -n security wazuh-manager-master-0 -c wazuh-manager -- /var/ossec/bin/wazuh-control status | grep -c "is running"`.
The 2026-11-06 baseline is `10`, including `wazuh-analysisd is running...`.
Record the number you get.

## 3) Steps

All edits are on `main`, committed with `git commit --only` (shared worktree).
After each commit, check `git log -1 --format=%s` before you push. No manual
`flux reconcile`: the push webhook drives Flux. If a stage has not started
rolling 5 min after the push, check the `security/wazuh` Kustomization's
`lastAppliedRevision` first. Each `sed` below was dry-tested on a scratch copy
under BSD sed (2026-11-06) and changes exactly one line. The resulting diffs
are quoted.

### Stage A — indexer

```bash
cd /Users/mu/code/cberg-home-nextgen
# Reduce translog replay on restart (no data change):
kubectl exec -n security wazuh-manager-master-0 -c wazuh-manager -- sh -c \
 'curl -s -k -u "$INDEXER_USERNAME:$INDEXER_PASSWORD" -X POST https://wazuh-indexer:9200/_flush' | head -c 200; echo
sed -i '' 's|image: wazuh/wazuh-indexer:4\.14\.9$|image: wazuh/wazuh-indexer:4.14.10|' \
  kubernetes/apps/security/wazuh/app/wazuh-indexer-statefulset.yaml
git diff kubernetes/apps/security/wazuh/app/wazuh-indexer-statefulset.yaml
#   64c64  <  image: wazuh/wazuh-indexer:4.14.9   >  image: wazuh/wazuh-indexer:4.14.10
printf 'fix(wazuh): indexer 4.14.9 -> 4.14.10 (plan wazuh-fleet-4.14.10, stage A/3, PR #491)\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n' > /tmp/wz-a.msg
git commit --only kubernetes/apps/security/wazuh/app/wazuh-indexer-statefulset.yaml -F /tmp/wz-a.msg
git log -1 --format=%s ; git show --stat HEAD | tail -3
git push
SHA_A=$(git rev-parse HEAD)
kubectl rollout status sts/wazuh-indexer -n security --timeout=10m
```
Then run **§4.1**. Do not start stage B until §4.1 passes.

### Stage B — manager

```bash
T_B=$(date -u +%Y-%m-%dT%H:%M:%SZ); T_B_LOG=$(date -u '+%Y/%m/%d %H:%M:%S')
sed -i '' 's|image: wazuh/wazuh-manager:4\.14\.9$|image: wazuh/wazuh-manager:4.14.10|' \
  kubernetes/apps/security/wazuh/app/wazuh-manager-statefulset.yaml
git diff kubernetes/apps/security/wazuh/app/wazuh-manager-statefulset.yaml
#   91c91  <  image: wazuh/wazuh-manager:4.14.9   >  image: wazuh/wazuh-manager:4.14.10
printf 'fix(wazuh): manager 4.14.9 -> 4.14.10 (plan wazuh-fleet-4.14.10, stage B/3, PR #491)\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n' > /tmp/wz-b.msg
git commit --only kubernetes/apps/security/wazuh/app/wazuh-manager-statefulset.yaml -F /tmp/wz-b.msg
git log -1 --format=%s ; git show --stat HEAD | tail -3
git push
SHA_B=$(git rev-parse HEAD)
kubectl rollout status sts/wazuh-manager-master -n security --timeout=10m
```
Then run **§4.2 and §4.3**. Do not start stage C until both pass.

### Stage C — dashboard + agents

```bash
T_C=$(date -u +%Y-%m-%dT%H:%M:%SZ)
sed -i '' 's|image: wazuh/wazuh-dashboard:4\.14\.9$|image: wazuh/wazuh-dashboard:4.14.10|' \
  kubernetes/apps/security/wazuh/app/wazuh-dashboard-deployment.yaml
sed -i '' 's|image: wazuh/wazuh-agent:4\.14\.9$|image: wazuh/wazuh-agent:4.14.10|' \
  kubernetes/apps/security/wazuh/app/wazuh-agents-daemonset.yaml
git diff kubernetes/apps/security/wazuh/app/wazuh-dashboard-deployment.yaml kubernetes/apps/security/wazuh/app/wazuh-agents-daemonset.yaml
#   19c19  <  image: wazuh/wazuh-dashboard:4.14.9  >  image: wazuh/wazuh-dashboard:4.14.10
#   41c41  <  image: wazuh/wazuh-agent:4.14.9      >  image: wazuh/wazuh-agent:4.14.10
printf 'fix(wazuh): dashboard + agent 4.14.9 -> 4.14.10 (plan wazuh-fleet-4.14.10, stage C/3, closes PR #491)\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n' > /tmp/wz-c.msg
git commit --only kubernetes/apps/security/wazuh/app/wazuh-dashboard-deployment.yaml kubernetes/apps/security/wazuh/app/wazuh-agents-daemonset.yaml -F /tmp/wz-c.msg
git log -1 --format=%s ; git show --stat HEAD | tail -4
git push
SHA_C=$(git rev-parse HEAD)
kubectl rollout status deploy/wazuh-dashboard -n security --timeout=10m
kubectl rollout status ds/wazuh-agent -n security --timeout=15m
```
Then run **§4.4–§4.6**. When everything passes:
`gh pr close 491 --comment "Applied in 3 ordered commits ($SHA_A, $SHA_B, $SHA_C) by plan wazuh-fleet-4.14.10."`
Renovate would otherwise rebase the PR into a no-op. Then
`rm -f /tmp/wz-unifi-sample.log /tmp/wz-?.msg`. Retire the plan file in the
same commit that sets it `executed`, per the README. Close the seven
`finding_refs` with `finding close <id> --commit $SHA_C`, but only after the
next security sweep shows the 4.14.10 images.

## 4) Verification

**Expected noise.** Each stage can briefly trip `WazuhIndexerPodNotReady` /
`WazuhManagerPodNotReady` / `WazuhDashboardDown` / `WazuhAgentDaemonSetNotReady`
(`for: 5m`) and `WazuhPodRestarted` (warning, `for: 1m`, but it counts restarts
of an existing pod, which a Recreate does not produce). These are expected
during a stage. They are a FAILURE if they are still firing 10 min after the
stage's rollout completed.

### 4.1 Stage A: indexer is the new image, green, and has the same data

```bash
kubectl get pod wazuh-indexer-0 -n security -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'
# PASS: ends in a digest != d8d5a842... (the 4.14.9 imageID); image tag 4.14.10
kubectl exec -n security wazuh-indexer-0 -c wazuh-indexer -- df -h /var/lib/wazuh-indexer | tail -1
# PASS: device /dev/longhorn/pvc-13694b98-... (FAIL: overlay = path.data regression -> empty indices)
```
Re-run the §2.2 block, retrying every 30 s for up to 5 min. Status goes
`red` → `yellow` → `green` while shards recover.

CONTENTS ASSERTION: the indexer holds the same data. **`INDICES` ≥ the §2.2
baseline and `ALERTDOCS` ≥ the §2.2 baseline**, with `STATUS green UNASSIGNED 0`,
`NONGREEN=0`, `PIPELINE=200` and `TEMPLATE=200`. This gate fails on an empty
or reset data dir: OpenSearch comes up `green` with only its own system
indices, so `INDICES` drops to a handful, `ALERTDOCS` reads 0 or errors, and
`PIPELINE` returns `404` (the 2026-07-12 failure, `wazuh-siem-recovery.md` §1).
`green` on its own is NOT the gate: an empty cluster is green.
CONTROL: alertname WazuhIndexerPodNotReady — must be not firing 10 min after
the stage-A rollout completes.

### 4.2 Stage B: manager is 4.14.10, ruleset loaded without errors, and its own start alert indexed

```bash
kubectl exec -n security wazuh-manager-master-0 -c wazuh-manager -- /var/ossec/bin/wazuh-control info | grep WAZUH_VERSION
# PASS: WAZUH_VERSION="v4.14.10"   (baseline 2026-11-06: "v4.14.9")
kubectl exec -n security wazuh-manager-master-0 -c wazuh-manager -- sh -c \
  "awk -v t='$T_B_LOG' '\$0 >= t' /var/ossec/logs/ossec.log | grep -i -c -E 'analysisd.*(error|critical)|\(5108\)|\(7621\)|duplicate'"
# PASS: 0. A (5108) means the ruleset was refused (would also stop analysisd); a duplicate-id
#       or XML error from a custom ConfigMap prints as "wazuh-analysisd: ERROR"/"CRITICAL".
kubectl exec -n security wazuh-manager-master-0 -c wazuh-manager -- /var/ossec/bin/wazuh-control status | grep -c "is running"
# PASS: matches the pre-roll count of running daemons. Measure it in §2 with the same command;
#       wazuh-analysisd absent from the "is running" list = ruleset failed to load.
```
CONTENTS ASSERTION: the manager's own start event went through
analysisd → alerts.json → filebeat → ingest pipeline → indexer. Query
`rule.id:502` with `@timestamp >= T_B` and `agent.name: wazuh-manager-master-0`:
```bash
kubectl exec -n security wazuh-manager-master-0 -c wazuh-manager -- sh -c "
U=\"\$INDEXER_USERNAME:\$INDEXER_PASSWORD\"
curl -s -k -u \"\$U\" -H 'Content-Type: application/json' 'https://wazuh-indexer:9200/wazuh-alerts-*/_count' \
 -d '{\"query\":{\"bool\":{\"filter\":[{\"term\":{\"rule.id\":\"502\"}},{\"range\":{\"@timestamp\":{\"gte\":\"$T_B\"}}}]}}}'"
```
PASS: `"count":1` or more within 5 min of the pod becoming Ready. Baseline:
the last 502 alert was 2026-11-03T02:37Z, the previous manager restart, so a
fresh one exists only if the post-roll pipeline works end to end. FAIL prints
`"count":0`. Then check filebeat with the SOP's `PIPELINE` check and the
`pipeline ... does not exist` symptom.
CONTROL: alertname WazuhManagerPodNotReady — not firing 10 min after the
stage-B rollout completes.

### 4.3 Stage B: the UniFi / Falco / envoy / local custom rules still load

```bash
kubectl exec -i -n security wazuh-manager-master-0 -c wazuh-manager -- /var/ossec/bin/wazuh-logtest < /tmp/wz-unifi-sample.log \
  | grep -i -E "id: '100103'|alert to be generated"
```
PASS: `id: '100103'` and `**Alert to be generated.` (the same as the §2.4
baseline). This gate can fail, as measured 2026-11-06. The example line in
the `unifi-decoder` ConfigMap comment (`... udr7 CEF:0|Ubiquiti|UniFi OS|4.3.9|...`)
returns `No decoder matched.` and no `id:` line. A ruleset that dropped
`etc/rules/unifi` or `etc/decoders/unifi` produces exactly that output. The
grep is case-insensitive because logtest mixes `**Alert` / `id:` casing.
Rule-ID uniqueness across all four ConfigMaps (`unifi-decoder`,
`envoy-decoder`, `wazuh-local-rules`, `wazuh-config` with 0 rules) is held by
premise `custom-rule-ids-unique`. A duplicate would surface here as an
analysisd ERROR in §4.2.

### 4.4 Stage C: real alert ingestion from every agent after the roll

CONTENTS ASSERTION: every agent's start alert (`rule.id:503`) and live feed
alerts arrive in `wazuh-alerts-*` with `@timestamp >= T_C`:
```bash
kubectl exec -n security wazuh-manager-master-0 -c wazuh-manager -- sh -c "
U=\"\$INDEXER_USERNAME:\$INDEXER_PASSWORD\"
curl -s -k -u \"\$U\" -H 'Content-Type: application/json' 'https://wazuh-indexer:9200/wazuh-alerts-*/_search' -d '{
 \"size\":0,\"query\":{\"range\":{\"@timestamp\":{\"gte\":\"$T_C\"}}},
 \"aggs\":{\"start\":{\"filter\":{\"term\":{\"rule.id\":\"503\"}},\"aggs\":{\"a\":{\"terms\":{\"field\":\"agent.name\"}}}},
          \"falco\":{\"filter\":{\"term\":{\"location\":\"/var/run/falco/falco.log\"}}},
          \"ctr\":{\"filter\":{\"prefix\":{\"location\":\"/host/var/log/containers/\"}}}}}'" \
| python3 -c "import sys,json; a=json.load(sys.stdin)['aggregations']; print('START', sorted(b['key'] for b in a['start']['a']['buckets'])); print('FALCO', a['falco']['doc_count']); print('CONTAINERLOG', a['ctr']['doc_count'])"
```
PASS within 20 min of `T_C`:
- `START ['k8s-nuc14-01', 'k8s-nuc14-02', 'k8s-nuc14-03']`;
- `FALCO` ≥ 1;
- `CONTAINERLOG` ≥ 1.

Baselines measured 2026-11-06 over 6 h: falco.log 176 alerts and container
logs 186 alerts (about 30/h each). Zero of either in 20 min is about 10× below
the floor. Rule 503 fires once per agent start, and its last occurrence was
2026-10-16, the previous agent roll. A missing node name means that agent did
not re-register, or its events never reached the indexer. `FALCO 0` means the
falco.log feed or the `unifi-decoder` Falco rules (1004xx) are broken.
`CONTAINERLOG 0` is the §1.3 regression.
CONTROL: alertname WazuhAgentDaemonSetNotReady — not firing 10 min after the
DaemonSet rollout completes.

### 4.5 Stage C: logcollector did not reject any monitored file (§1.3)

```bash
for p in $(kubectl get pods -n security -l app=wazuh-agent -o name); do
  echo "== $p"
  kubectl exec -n security "${p#pod/}" -- sh -c '/var/ossec/bin/wazuh-control info | grep WAZUH_VERSION;
    echo REJECT=$(grep -c "(1103)" /var/ossec/logs/ossec.log);
    echo CTRFILES=$(grep -c "host/var/log/containers/" /var/ossec/logs/ossec.log)'
done
```
PASS on each of the 3 pods: `WAZUH_VERSION="v4.14.10"`, `REJECT=0` and
`CTRFILES` > 0. The agent's `ossec.log` is on the container overlay, so it
starts empty at pod start and the count covers only the new version. FAIL
reads `REJECT=N` with lines like
`(1103): Could not open file '/host/var/log/containers/...' due to [(1)-(Operation not permitted)]`.
That is the new vetting refusing our symlinks, and §4.4 `CONTAINERLOG` will
also read 0. Baseline on 4.14.9 (2026-11-06): `REJECT=0`.

### 4.6 Stage C: dashboard serves and reaches the indexer

```bash
kubectl port-forward -n security svc/wazuh-dashboard 15601:5601 >/dev/null 2>&1 & PF=$!; sleep 3
curl -sk -o /dev/null -w "root=%{http_code}\n" https://localhost:15601/
curl -sk -o /dev/null -w "status=%{http_code}\n" https://localhost:15601/api/status
kill $PF 2>/dev/null
```
PASS: `root=302` (redirect to SAML login) and `status=401` (unauthenticated,
answered by the security plugin, which needs the indexer). FAIL is `503`
("server is not ready yet", dashboard cannot reach the indexer) or `000`.
Baseline 2026-11-06: 302 / 401. Then run
`kubectl logs -n security deploy/wazuh-dashboard --since=10m | grep -c -i ResponseError`.
It must not exceed the pre-existing rate. The baseline is 14 per 30 min, a
known pre-existing loop (`F-d4bc2fa7`), not caused by this change.
CONTROL: alertname WazuhDashboardDown — not firing 10 min after the dashboard
rollout completes.
CONTROL: alertname WazuhPodCrashLooping — not firing at the end of the window
for any `wazuh-*` pod.

## 5) Rollback

### 5.1 Known-good references
4.14.9 imageIDs live on 2026-11-06 (cached on the nodes):
- indexer `sha256:d8d5a842e14f2933417e0eb8f5725cf4f7dd2abffe3ccc385c1145b990785f2d`
- manager `sha256:a63fc6a0195eacaf73829d8beb5e57dc195d42f61c6c3feb896f1062ac198c26`
- dashboard `sha256:5230e95b3deecb7fa4ae7768d88fb03c660bf3c81f1732042a5439d1c3d3c760`
- agent `sha256:9337101ff6f05a4872698bab79ca6c101ecb0d7d8fbb1a6ae60ca1f93c38e994`

### 5.2 Revert path (git-revert class)
Revert in REVERSE stage order, so that an agent is never newer than its
manager and the dashboard never leads the manager. Revert only the stages that
landed:
```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit $SHA_C   # if stage C landed
git revert --no-edit $SHA_B   # if stage B landed
git revert --no-edit $SHA_A   # if stage A landed
git log -3 --format=%s ; git push
```
A failed stage reverts alone; earlier passed stages may stay. Example: a §4.5
`REJECT>0` failure reverts only `$SHA_C`. A 4.14.9 agent against a 4.14.10
manager is a supported skew. Confirm the cluster is back: all four pods show
the §5.1 imageIDs, and the §2.2 block, §4.2 (WAZUH_VERSION v4.14.9) and §4.4
(with `T_C` reset to the revert time) pass.

**Indexer downgrade on the same data dir is safe** because both versions run
OpenSearch 2.19.6 (§1.2). **Manager downgrade is safe** because no wazuh-db
schema change exists between the tags, and the PVC's `/var/ossec/etc` holds
our config, not the version-specific ruleset (that lives in the image under
`/var/ossec/ruleset`).

### 5.3 If indexer data is lost or corrupt (forward-only damage)
The signs are §4.1 showing `INDICES` far below baseline, `ALERTDOCS` 0, or
`red` with unassigned primaries that do not recover in 10 min. That is DATA
LOSS, so escalate to the operator before acting. Ingestion can be restored
non-destructively first with `wazuh-siem-recovery.md` §4
(`filebeat setup --index-management --pipelines`), which recreates only the
pipeline and template. Restoring history uses the Longhorn backup named in
§2.3 for volume `pvc-13694b98-5c6d-4fb5-b3a7-cb9837e2cabb`, following
`docs/sops/backup.md` / `docs/sops/longhorn.md`: scale the StatefulSet to 0
via git, restore the backup in place, scale back. Events since the 23:00 UTC
backup are lost; the window agent must not run this unattended.

## 6) Interference notes

- **SIEM-wide outage, short.** Stage A stops indexer writes for about 2–3 min.
  Filebeat buffers and retries, and `alerts.json` stays on the manager PVC, so
  nothing is dropped unless a document is permanently rejected. Stage B stops
  event analysis for about 2 min, and agents queue client-side. Stage C rolls
  one agent at a time. The security sweep's "agent silent >2h" check is not
  affected by a 55 min window.
- **Falco feed.** Falco keeps writing `falco.log` on the host. The agent
  resumes from its position after the roll. A same-window Falco roll
  (`flux-oci-chart-sources` stage 3) would confound §4.4: hence the conflict.
- **Longhorn.** Two RWO volumes detach and re-attach (StatefulSets, so no
  Multi-Attach risk). The dashboard Deployment has no PVC, so its default
  `RollingUpdate` is safe. Do not share a window with `longhorn-1.13.0` or
  `talos-linux-1.14.5` (both are already `exclusive`; listed for explicitness).
- **Prometheus.** §4 reads only the `wazuh-alerts` PrometheusRule alerts. No
  `kube-prometheus-stack` plan is open on 2026-11-06. If one is added for the
  same night, it must be added to `conflicts_with` on both sides.
- **Execution class.** `capability_change: false`, `rollback_class: git-revert`,
  no reboot, and no SD-11 floor token in `touches.shared`. Once reviewed, it
  is eligible for the unattended `nightly` window (55 ≤ 70 min schedulable),
  except for §5.3, which always stops for the operator.
- **Reciprocity owed.** `flux-oci-chart-sources` does not yet list this plan in
  its `conflicts_with`. The planner did not edit it (single-file rule), so the
  sweep or window agent must add the reciprocal entry.
