---
plan_id: open-webui-17.0.0
component: open-webui
pr: 334                               # chart PR: feat(helm)!: Update open-webui ( 16.6.0 -> 17.0.0 ). Stays
                                      # UNMERGED; Renovate closes it once the pin lands by direct commit.
kind: chart
current: "chart open-webui 16.6.0 (image already v0.12.3 after open-webui-0.12.3)"
target: "chart open-webui 17.0.0 (appVersion 0.12.0; newest stable, 17.0.1-dev.* are dev builds)"
update_type: major                    # semver major on paper; rendered effect is labels only (§1.2)
risk: low                             # label-only manifest diff, values schema unchanged, image pinned in
                                      # values, no DB touch. Costs one more STS + redis roll (~2 min).
est_duration_min: 20                  # pre-checks 5, commit+reconcile+roll 8, verification 5, slack 2
needs_reboot: false
touches:
  namespaces: [ai]
  resources:
    - helmrelease/open-webui
    - statefulset/open-webui            # pod-template labels change -> pod rolls once (same image v0.12.3)
    - deployment/open-webui-redis       # pod-template labels change -> rolls once (ephemeral pub/sub only)
    - service/open-webui                # labels only
    # NOT touched: deployment/open-webui-pipelines (subchart rendered byte-identical), pvc/*,
    # httproute/open-webui (selector/port unchanged), the DB.
  shared: [monitoring]                  # §4.3 reads Prometheus (kube-state-metrics), the window's instrument.
depends_on:
  - open-webui-0.12.3                   # HARD ORDER. The image plan migrates the DB to head 0bd252b206fb and
                                        # pins image.tag v0.12.3 in values. If this chart ran first nothing
                                        # breaks (tag is pinned) but the rollback boundaries blur; if the
                                        # tag pin were ever lost the chart default v0.12.0 would be a
                                        # downgrade across migrations. Premise image-migrated fails closed.
conflicts_with:
  - open-webui-0.12.2                   # superseded sibling; never both.
  - redis-fleet-8.10.2                  # edits the SAME file (websocket.redis.image.tag), rolls redis + STS.
  - flux-oci-chart-sources              # re-points the open-webui chart source (inventory pins 16.5.0).
  - helm-drift-detection                # asserts Helm revisions identical before/after; this creates one.
  - kube-prometheus-stack-92.2.0        # §4.3 reads kube-state-metrics through Prometheus.
  - kube-prometheus-stack-92.10.1       # same instrument.
  - flux-reconciler-impersonation       # changes WHO applies the HelmRelease this plan relies on.
  - flux-fleet-0.60.0                   # Flux controller upgrade under this plan's GitOps step.
  - flux-distribution-2.9.6             # same, distribution-wide.
  - envoy-proxy-config-distroless-v1.39.3  # §4.5 reads the app through envoy-external.
  - envoy-proxy-config-distroless-v1.39.4  # same.
  - envoy-proxy-config-distroless-v1.40.0  # same.
exclusive: false
security_ref: F-f3caadda              # umbrella image-scan finding handled by the image plan; the chart adds
                                      # no image change. Detail stays in sweep_history.
capability_change: false              # rendered diff is metadata labels only; no new route, port, env,
                                      # permission or feature (§1.2). A truthful false.
rollback_class: git-revert            # label-only, no schema or data touched; git revert + reconcile fully
                                      # restores it. (The DB is NOT touched by this plan.)
backup_gate: "Completed Longhorn backup of open-webui-20g < 26h (runbooks/longhorn-backup-age.py --max-hours 26 open-webui-20g exits 0). No DB copy needed: this plan never writes the DB, and the image plan's webui.db.pre-0.12.3 copy already exists beside it."
finding_refs:
  - F-3cdb3585                        # version: chart 16.6.0 -> 17.0.0
review: ready-for-go@2026-10-22   # plan-reviewer 2026-10-22: ready-for-go once open-webui-0.12.3 landed (render diff = chart/version labels only); fixes applied by planner
status: vetted
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-22"                # rewritten 2026-10-22 as chart-only; the old draft moved the image to
                                      # v0.12.0 and is obsolete
premises:
  - id: image-migrated
    why: >-
      The image plan must have landed: the StatefulSet runs v0.12.3. If it still runs v0.11.4 the
      depends_on order was violated; SKIP this plan (do not run the chart first).
    run: kubectl get sts -n ai open-webui -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/open-webui/open-webui:v0.12.3
  - id: chart-current
    why: The HelmRelease must still pin 16.6.0; the §3.2 sed matches only that line.
    run: kubectl get helmrelease -n ai open-webui -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: 16.6.0
  - id: chart-pin-unique
    why: The sed edits by exact line; the version line must occur exactly once in the repo file.
    run: 'grep -c -E "^      version: 16\.6\.0$" kubernetes/apps/ai/open-webui/app/helmrelease.yaml'
    expect_exact: "1"
  - id: tag-pinned-in-values
    why: >-
      image.tag must be pinned to v0.12.3 in values. Chart 17 defaults to appVersion 0.12.0; a missing
      pin would downgrade across the migrations.
    run: 'grep -c -E "^      tag: v0\.12\.3$" kubernetes/apps/ai/open-webui/app/helmrelease.yaml'
    expect_exact: "1"
  - id: hr-ready
    why: A HelmRelease already failing would mask whether this upgrade broke it.
    run: kubectl get helmrelease -n ai open-webui -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
---

# open-webui chart 16.6.0 → 17.0.0 (chart only; runs after open-webui-0.12.3)

## 1. Summary & why held

### 1.1 Why held

Renovate flags it because it is a semver MAJOR (`feat(helm)!`), and the auto-updater refuses majors.
Upstream's chart 17.0.0 CHANGELOG entry is one line, "Updated chart appVersion to v0.12.0", plus a
generic BREAKING note deferring to the app's release notes (the app half is the image plan).

### 1.2 Investigation: is the major actually breaking for us? No (rendered 2026-10-22)

`helm template open-webui open-webui/open-webui -n ai -f <live spec.values>` for 16.6.0 and 17.0.0
(both exit 0, 304 lines each). `diff` of the two renders:

```
- helm.sh/chart: open-webui-16.6.0           + helm.sh/chart: open-webui-17.0.0              (x7)
- app.kubernetes.io/version: "0.11.4"        + app.kubernetes.io/version: "0.12.0"           (x7)
```

and nothing else. (Rendered with the CURRENT repo values, so the image lines read v0.11.4 on both
sides because the tag is pinned; after the image plan both read v0.12.3.) Further checks:

- `helm show values` 16.6.0 vs 17.0.0: diff empty. No value keys renamed, removed or added, so our
  `values:` block needs NO change.
- Kinds and shape unchanged: still a StatefulSet (`updateStrategy` RollingUpdate partition 0), PVC via
  `existingClaim: open-webui-20g`, websocket redis as a Deployment (`open-webui-redis`), pipelines
  subchart enabled, ollama subchart disabled (we use `ollamaUrls`), Service LoadBalancer
  192.168.55.28, no Ingress rendered, the HTTPRoute is our own file outside the chart.
- Conclusion: **safe to run unattended** once the image plan has landed. No value change, no data
  migration. The only runtime effect is that pod-template labels change, so `statefulset/open-webui`
  and `deployment/open-webui-redis` each roll once on the same images. Redis holds only ephemeral
  websocket/lock keys. Pipelines does not roll.
- The `app.kubernetes.io/version` label will read `0.12.0` while the image is v0.12.3 (chart appVersion;
  cosmetic).

### 1.3 Live facts (2026-10-22)

- Chart 16.6.0 deployed (Helm rev 56, `maxHistory: 1`), image v0.11.4 today (image plan not yet run).
- `upgrade.remediation.retries: 1` in the HelmRelease.
- No probes on the STS pod ("Ready" proves nothing; §4 does not use it).

## 2. Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 runbooks/plan-premises.py open-webui-17.0.0
#   PASS: all premises OK. Newest-chart check (not a premise, tooling refuses it): `helm search repo open-webui/open-webui --versions | sed -n 2,4p` must show 17.0.0 as the newest non-dev row.
#   image-migrated FAIL = the image plan has not run: SKIP, do not proceed.

.venv/bin/python3 runbooks/longhorn-backup-age.py --max-hours 26 open-webui-20g; echo "exit=$?"
#   PASS: "FRESH", exit=0. FAIL prints STALE/MISSING, exits non-zero.

# the live DB is at the new head (the image plan's end state) and the app is healthy
kubectl exec -n ai open-webui-0 -c open-webui -- python3 -c "
import sqlite3; c=sqlite3.connect('file:/app/backend/data/webui.db?mode=ro',uri=True)
print('ALEMBIC', c.execute('select version_num from alembic_version').fetchone()[0])
print('CHATS', c.execute('select count(*) from chat').fetchone()[0])" | tee /tmp/owui-chart-pre.txt
#   PASS: ALEMBIC 0bd252b206fb. Anything else: STOP (image plan incomplete or rolled back).
helm history open-webui -n ai --max 1       # PASS: STATUS deployed
flux get helmreleases -n ai open-webui      # PASS: READY True
git fetch -q && git status -sb | head -1    # main not behind origin
```

## 3. Steps

### 3.1 Update marker (skip if the image plan's marker is still set in this window)

```bash
runbooks/update-marker.sh add open-webui ai 1 "open-webui chart 16.6.0->17.0.0"
```

### 3.2 The edit (one commit; retries 0 for the attempt)

Dry-tested on a scratch copy of the live file with BSD sed on macOS 2026-10-22 (the repo file still has
`tag: v0.11.4` today because the image plan has not run; the lines edited here are unaffected). Diff:

```
11c11   <       version: 16.6.0     >       version: 17.0.0
25c25   <       retries: 1          >       retries: 0      (upgrade: block; install retries: 3 untouched)
```

```bash
F=kubernetes/apps/ai/open-webui/app/helmrelease.yaml
sed -i '' \
  -e 's/^      version: 16\.6\.0$/      version: 17.0.0/' \
  -e '/^  upgrade:$/,/^  uninstall:$/s/^      retries: 1$/      retries: 0/' \
  "$F"
git diff --stat -- "$F"     # PASS: 1 file, 2 insertions(+), 2 deletions(-)
yq '.spec.chart.spec.version, .spec.values.image.tag, .spec.upgrade.remediation.retries' "$F"
#   PASS, in order: 17.0.0 / v0.12.3 / 0   (a tag other than v0.12.3 = STOP, do not commit; git checkout -- "$F")

MSG=$(mktemp /tmp/owui-chart-msg.XXXXXX)
cat > "$MSG" <<'EOF'
feat(open-webui): chart 16.6.0 -> 17.0.0

Plan open-webui-17.0.0 (after open-webui-0.12.3). Rendered diff vs
16.6.0 with live values is labels only; values schema unchanged; image
stays pinned. upgrade.remediation.retries 0 for the attempt (restored
after verification). Satisfies Renovate #334.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
git commit --only "$F" -F "$MSG"
git log -1 --format=%s      # MUST be "feat(open-webui): chart 16.6.0 -> 17.0.0" (message-swap guard)
git show --stat HEAD        # exactly that one file
git push; rm -f "$MSG"
```

Flux applies via the webhook; manual `flux reconcile helmrelease -n ai open-webui --with-source` only if
nothing happened after 10 minutes.

### 3.3 Watch the roll

```bash
for i in $(seq 1 30); do
  L=$(kubectl get sts -n ai open-webui -o jsonpath='{.spec.template.metadata.labels.helm\.sh/chart}')
  PH=$(kubectl get pod -n ai open-webui-0 -o jsonpath='{.status.phase}' 2>/dev/null)
  REV=$(kubectl get pod -n ai open-webui-0 -o jsonpath='{.metadata.labels.controller-revision-hash}' 2>/dev/null)
  echo "$L $PH $REV"; [ "$L" = "open-webui-17.0.0" ] && [ "$PH" = "Running" ] && break
  sleep 15
done
```

If the STS template is not on `open-webui-17.0.0` with a Running pod after ~8 min, go to §5.

### 3.4 After §4 passes: restore retries (second commit)

```bash
sed -i '' -e '/^  upgrade:$/,/^  uninstall:$/s/^      retries: 0$/      retries: 1/' "$F"
git diff -- "$F" | grep -E '^[-+] '     # PASS: exactly "-      retries: 0" / "+      retries: 1"
MSG=$(mktemp /tmp/owui-chart-msg.XXXXXX); printf 'chore(open-webui): restore upgrade remediation retries after chart 17.0.0\n\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>\n' > "$MSG"
git commit --only "$F" -F "$MSG"; git log -1 --format=%s; git show --stat HEAD; git push; rm -f "$MSG"
runbooks/update-marker.sh clear open-webui
```

No pod roll from this commit (spec fields that do not render); `open-webui-0` startTime unchanged.
Then: confirm Renovate closed PR 334 (close by hand after 24 h); `policy-cli.py finding close F-3cdb3585
--commit <sha>`.

## 4. Verification

Run after §3.3. Each gate can FAIL; the failure output is noted.

**4.0 Timing guard (run first).**
```bash
S=$(kubectl get pod -n ai open-webui-0 -o jsonpath='{.status.startTime}')
AGE=$(python3 -c "import sys,datetime as d;print(int((d.datetime.now(d.timezone.utc)-d.datetime.fromisoformat(sys.argv[1].replace('Z','+00:00'))).total_seconds()))" "$S")
echo "POD_AGE_S $AGE"
[ "$AGE" -ge 300 ] || { echo "WAIT $((300-AGE))s"; sleep $((300-AGE)); }
```
PASS: pod at least 300 s old before 4.3/4.4, otherwise a zero restart count and an empty log are vacuous.

**4.1 Chart and image actually live**
```bash
kubectl get helmrelease -n ai open-webui -o jsonpath='{.status.history[0].chartVersion}{" "}{.status.history[0].status}{"\n"}'
kubectl get sts -n ai open-webui -o jsonpath='{.spec.template.metadata.labels.helm\.sh/chart}{" "}{.spec.template.spec.containers[0].image}{"\n"}'
kubectl get pod -n ai open-webui-0 -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'
```
- PASS: `17.0.0 deployed`, then `open-webui-17.0.0 ghcr.io/open-webui/open-webui:v0.12.3`, then an imageID
  ending `a537bbe1e6b428820f52ed4a029d7fff97062e24d5cf32c365fba36fd0542def`.
- FAIL: chart `16.6.0` (not applied), image `v0.12.0` (tag pin lost, would be a migration downgrade, go
  to §5 and escalate), imageID differing (wrong build).

**4.2 App serves and data untouched**
```bash
kubectl exec -n ai open-webui-0 -c open-webui -- python3 -c "
import sqlite3,urllib.request; print(urllib.request.urlopen('http://localhost:8080/api/version').read().decode())
c=sqlite3.connect('file:/app/backend/data/webui.db?mode=ro',uri=True)
print('ALEMBIC', c.execute('select version_num from alembic_version').fetchone()[0])
print('CHATS', c.execute('select count(*) from chat').fetchone()[0])"
```
- PASS: `"version":"0.12.3"`, `ALEMBIC 0bd252b206fb`, and CHATS >= the `/tmp/owui-chart-pre.txt` value
  (chats only grow). FAIL: connection refused/traceback (crash loop), another version, a lower CHATS.

**4.3 No crash loop, redis back.** Pod has no probes, so these are the liveness evidence.

CONTROL: metric kube_pod_container_status_restarts_total — `{namespace="ai",pod="open-webui-0",container="open-webui"}` must read 0 at least 5 min after the new pod started (recreated pod, counter restarts at 0). FAIL: >=1.

CONTROL: metric kube_deployment_status_replicas_available — `{namespace="ai",deployment="open-webui-redis"}` == 1. FAIL: 0 (redis roll stuck).

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
for q in 'kube_pod_container_status_restarts_total{namespace="ai",pod="open-webui-0",container="open-webui"}' \
         'kube_deployment_status_replicas_available{namespace="ai",deployment="open-webui-redis"}'; do
  curl -s -G localhost:19090/api/v1/query --data-urlencode "query=$q" | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print('N',len(r),[x['value'][1] for x in r])"
done
kill $PF 2>/dev/null
```
- PASS: `N 1 ['0']` then `N 1 ['1']`. `N 0 []` is a FAIL (instrument read nothing), never a pass.

**4.4 Logs clean and websocket path alive**
```bash
kubectl logs -n ai open-webui-0 -c open-webui --since=15m | grep -i -c -E "error running migrations|can't locate revision|traceback|noperm"
kubectl logs -n ai open-webui-0 -c open-webui --since=15m | grep -i -c -E "started server|application startup|uvicorn running|alembic"   # positive control
kubectl exec -n ai deploy/open-webui-redis -- redis-cli --scan --pattern 'open-webui:*' | wc -l
```
- PASS: `0` errors AND a positive-control count >= 1 (the pod's own startup lines are in the window; 0 means the window missed the start = FAIL, not pass), then >=1 redis keys five minutes after start (the redis pod restarted empty and the app repopulates it;
  baseline 4 keys). FAIL: any hit in the first, `0` keys in the second (app not talking to redis).

**4.5 Public path, login surface, Ollama (behaviour, unattended)**
```bash
H=$(kubectl get httproute -n ai open-webui -o jsonpath='{.spec.hostnames[0]}')
curl -s -o /dev/null -w '%{http_code}\n' "https://$H/health"
curl -s "https://$H/api/config" | python3 -c "
import sys,json; d=json.load(sys.stdin)
print('VERSION', d.get('version')); print('AUTH', d['features']['auth']); print('OAUTH', sorted(d.get('oauth',{}).get('providers',{}).keys()))"
kubectl exec -n ai open-webui-0 -c open-webui -- python3 -c "
import urllib.request,json,os
u=os.environ['OLLAMA_BASE_URLS'].split(';')[0].rstrip('/')
print('OLLAMA_MODELS', sorted(m['name'] for m in json.load(urllib.request.urlopen(u+'/api/tags',timeout=10))['models']))"
```
- PASS: `200`; `VERSION 0.12.3 / AUTH True / OAUTH []`; `OLLAMA_MODELS ['gemma4:26b-mlx',
  'nomic-embed-text:latest']`.
- FAIL: 5xx (envoy backend down), non-JSON from `/api/config`, `AUTH False` (open instance), version
  other than 0.12.3, a connection error to Ollama. There is no OIDC/Authentik redirect to test: the
  pod has no OAUTH/OIDC env and the route has no Authentik SecurityPolicy (local auth), verified live
  2026-10-22; a non-empty OAUTH list would be a change and a FAIL.
- A different model list is a host-side drift (the Mac mini changes it), not an upgrade failure: record
  it, do not roll back on it alone.

Operator/Chrome check (attended only; a nightly run records it pending): log in, open an old chat, send one
short prompt to `gemma4:26b-mlx`, reload once and confirm no reconnect loop.

## 5. Rollback

Operator-away rule: any FAIL in §3.3 or §4 (except the Ollama host-drift note) runs this git revert at once, without waiting for a person; if both commits landed, revert both SHAs, newest first.

Label-only change, DB untouched: a git revert is complete.

```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/ai/open-webui/app/helmrelease.yaml
SHA=$(git log -1 --format=%H --grep='^feat(open-webui): chart 16.6.0 -> 17.0.0$' -- "$F")
git show --stat "$SHA"      # confirm it is the §3.2 commit and ONLY that file
MSG=$(mktemp /tmp/owui-chart-revert.XXXXXX); printf 'revert: open-webui chart back to 16.6.0 (plan open-webui-17.0.0 rollback)\n\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>\n' > "$MSG"
git revert --no-commit "$SHA" && git commit --only "$F" -F "$MSG"
git log -1 --format=%s; git show --stat HEAD; git push; rm -f "$MSG"
```

If §3.4 had already landed, also restore `retries: 1` (`yq '.spec.upgrade.remediation.retries' "$F"`).
Confirm back: re-run §4.1 (expect `16.6.0 deployed`, image still `v0.12.3`; do NOT revert the image here,
the DB is already at the new head) and §4.2-§4.4.

Helm wedged `pending-upgrade`: application-update SOP §7/§11; `helm rollback open-webui <rev> -n ai
--wait=false` only if that revision still exists (`maxHistory: 1`). Restoring the DB is never needed for
this plan; if §4.2 shows the DB lost data, the image plan's §5 procedure (`webui.db.pre-0.12.3`) applies.

## 6. Interference notes

- **Order:** `depends_on: open-webui-0.12.3` (planner skips this plan while that one is unmet). Same
  window is fine (about 45 + 20 min): run the image plan to its §3.5 first, then this plan.
- Both plans edit `helmrelease.yaml`; they must never be committed concurrently. `redis-fleet-8.10.2`
  also edits it (`websocket.redis.image.tag`): serialize.
- `flux-oci-chart-sources` inventories this chart at 16.5.0: after this plan it must pin 17.0.0 or its
  move is a chart downgrade.
- Shared surfaces: `monitoring` (Prometheus read in §4.3, hence the kube-prometheus-stack plans in
  `conflicts_with`), and the public edge only as a reader (envoy plans listed).
- Execution class: `capability_change: false` and `rollback_class: git-revert` with `risk: low` makes
  this eligible for the unattended low-risk path once reviewed and the dependency is satisfied.
