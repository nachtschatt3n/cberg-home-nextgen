---
plan_id: mqttx-web-v1.13.1
component: mqttx-web
pr: null                              # no Renovate PR; reached the PLAN lane via coverage.py's
                                      # no-PR direct-bump path (nightly window 2026-09-25, Step 0.5)
kind: image
current: "v1.13.0"                    # live on deployment/mqttx-web, imageID index digest
                                      # sha256:64525ad9… (measured 2026-09-25)
target: "v1.13.1"                     # GitHub release 2026-09-20T07:12Z (not prerelease);
                                      # Docker Hub tag pushed 2026-09-20T07:14Z, index digest
                                      # sha256:e777a2221a4e92ea0b87b3170a96ae09d4e557d2dc80c694175669762f47cfd0
update_type: patch
risk: low                             # The hold is a FALSE POSITIVE for this image (§1.2): the
                                      # flagged TypeORM migration lives in the Electron DESKTOP
                                      # tree (src/), the image is built from web/ only, and the
                                      # workload is a stateless static file server with no volume.
est_duration_min: 10                  # edit+commit+push 2, reconcile+Recreate ~2, verification 5
needs_reboot: false
touches:
  namespaces: [home-automation]
  resources:
    - helmrelease/mqttx-web
    - deployment/mqttx-web
    - service/mqttx-web
    - httproute/mqttx-web
    - "docker.io/emqx/mqttx-web"
  shared: []                          # DELIBERATE. Leaf web UI: no PVC, no DB, no Secret, no
                                      # Authentik provider, nothing in-cluster depends on it.
                                      # The HTTPRoute object is not modified (chart 5.1.0 and
                                      # route values unchanged) so gateway/envoy is not perturbed;
                                      # §4.3 only READS through envoy-internal.
depends_on: []
conflicts_with:
  - kube-prometheus-stack-91.4.1      # §4.4 reads Prometheus (kube-state-metrics series); a
                                      # restarting/replaying Prometheus answers "no series", which
                                      # the §4.4 gate treats as FAIL -> needless revert.
  - talos-1.14.1                      # node roll reboots every node: pod would be rescheduled
                                      # mid-verification and Prometheus/KSM go blind.
exclusive: false
security_ref: F-2b88c402              # disposition after the bump is decided on the finding record (re-measured 2026-09-26, detail there); closing it is not a step of this plan.
capability_change: true               # HONEST, not convenient: upstream v1.13.1 lists
                                      # user-visible Web features (collapsible connections pane,
                                      # MQTT 5.0 subscription user properties). Additive only, no
                                      # config/contract change here — the operator may reclassify.
rollback_class: git-revert            # stateless: no server-side data is written or migrated (§1.2)
finding_refs: [F-2b88c402, F-e0347d36]
                                      # F-2b88c402 (security, new, last seen 2026-09-24) names the
                                      # running v1.13.0 tag and says a newer upstream tag exists; see the record for the 2026-09-26 re-measurement.
                                      # F-e0347d36 (version, "mqttx-web: image emqx/mqttx-web
                                      # v1.13.0 → v1.13.1 (patch)") — producer=script, auto-closes
                                      # once the pin moves.
status: vetted   # 2026-09-26 plan-reviewer needs-fix -> fixed (256Mi, OOM gate, ks namespace); re-review needs-fix (2.3 must not load the old pod) -> fixed; ready-for-go
window: "now:2026-09-26"   # ON-DEMAND NOW run 2026-09-26 (run-now.py stamp; was None)
premises:
  - id: live-image-still-v1.13.0
    why: >-
      `current:` claims v1.13.0. If the cluster already moved (e.g. a later
      window direct-bumped it), this plan is a no-op: run §4 and retire it.
    run: kubectl get deploy -n home-automation mqttx-web -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: emqx/mqttx-web:v1.13.0
  - id: git-pin-still-v1.13.0
    why: "The §3 edit and the §5 revert both assume main pins exactly one v1.13.0 tag line."
    run: "git show HEAD:kubernetes/apps/home-automation/mqttx-web/app/helmrelease.yaml | grep -c 'tag: v1.13.0'"
    expect_exact: "1"
  - id: helmrelease-ready
    why: "Do not stack a bump on an already-failing release."
    run: kubectl get helmrelease -n home-automation mqttx-web -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: chart-still-app-template-5.1.0
    why: "The analysis covers an image-only delta; a chart change would alter rendered objects (route, service)."
    run: kubectl get helmrelease -n home-automation mqttx-web -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "5.1.0"
  - id: workload-has-no-volumes
    why: >-
      Guards the whole risk argument: the pod mounts NOTHING, so the image can
      hold no server-side state for any migration to touch. If a volume ever
      appears, re-assess §1.2 before executing.
    run: kubectl get deploy -n home-automation mqttx-web -o jsonpath='{.spec.template.spec.volumes}' | wc -c | tr -d ' '
    expect_exact: "0"
  - id: no-mqttx-pvc
    why: "Same argument, storage side: no PVC for this app exists in the namespace."
    run: kubectl get pvc -n home-automation -o name | grep -c -i mqttx
    expect_exact: "0"
  - id: strategy-recreate
    why: "Rollout shape assumed in §4 (single pod replaced, brief gap, no surge twin)."
    run: kubectl get deploy -n home-automation mqttx-web -o jsonpath='{.spec.strategy.type}'
    expect_exact: Recreate
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/gateway-api-httproute.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/auto-update.md
generated: "2026-09-25"
---

# mqttx-web v1.13.0 → v1.13.1

## 1. Summary & why held

### 1.1 What changes
Two lines in `kubernetes/apps/home-automation/mqttx-web/app/helmrelease.yaml`:
`tag: v1.13.0` → `tag: v1.13.1`. Chart (app-template 5.1.0), Service, HTTPRoute
and Homepage annotations are untouched. The image is the MQTTX **web** client:
a static Vue bundle served by `http-server -p 80` on `node:18-alpine`.

Image config compared for both tags from the Docker Hub registry (amd64, 2026-09-25):
`Entrypoint [docker-entrypoint.sh]`, `Cmd [http-server -p 80]`, `WorkingDir /app`,
`ExposedPorts 80/tcp`, `User` unset, `NODE_VERSION=18.20.8` — **identical**. The four base layers (alpine + node) are byte-identical; the `npm i -g http-server` layer and the `COPY dist ./` layer (the built bundle) were rebuilt. So the runtime contract the
chart relies on (port 80, root user inside `drop: ALL`) does not move.

### 1.2 Why held — and why it does not apply to this image
coverage.py reason: *"G3 structural signal — migration/schema change in the diff:
new migration file src/database/migration/1783562195464-koLang.ts"*.

MQTTX is a monorepo with three products: Electron desktop (`src/`), CLI (`cli/`),
web (`web/`). The v1.13.0…v1.13.1 compare is 32 commits / 71 files. Evidence that
the flagged migration is **desktop-only** and cannot reach this image:

- The migration is a TypeORM `MigrationInterface` that rebuilds the SQLite table
  `SettingEntity` to widen the `currentLang` CHECK to include `'ko'` (Korean
  language, a Desktop-only feature per the release notes). It lives in `src/`.
- `.github/workflows/deploy_web.yaml` (job `publish_docker`) runs
  `yarn && yarn build:docker` in `web/` and builds with `context: ./web`;
  `web/Dockerfile` is `FROM node:18-alpine` / `COPY dist ./`. `web/tsconfig.json`
  maps `@/*` → `web/src/*`. `web/package.json` has `lowdb` and no `typeorm`.
- Web state lives in the **browser**: `web/src/database/index.ts` is
  `Lowdb(new LocalStorage('db'))`. The only web-side "schema" change in this
  release is additive and idempotent:
  `if (!this.db.has('settings.showConnectionList').value()) { this.db.set('settings.showConnectionList', true).write() }`.
  It writes a default key into each user's own browser localStorage on first
  load; v1.13.0 ignores an unknown key, so a rollback leaves it inert.
- Server side: the pod has no volumes and no env (premises
  `workload-has-no-volumes`, `no-mqttx-pvc`) — there is nothing to migrate.

**Verdict: false positive.** The structural gate reads the whole repo diff, not
the build context of the image it is gating.

### 1.3 Upstream release notes (v1.13.1, 2026-09-20)
Web-relevant items: *"Support MQTT 5.0 user properties for subscriptions"*,
*"Enhance data export with message-based progress tracking"*,
*"Add collapsible connections list pane"* (Web), plus fixes in the
"Desktop,Web" section including security fixes. No breaking change, no config
change, no removed option. This is a routine patch bump plus the OOM fix in §3.1b; the security disposition lives on `F-2b88c402`, not in this plan.

### 1.4 Repo correction (not fixed by this plan)
The pin comment in `helmrelease.yaml` —
`# v1.13.3 is a GitHub release only; not published to Docker Hub (latest image tag is v1.13.0)`
— is wrong on both counts as of 2026-09-25: there is no v1.13.3 release at all
(GitHub releases: v1.13.1, v1.13.0, v1.12.1…), and v1.13.1 IS on Docker Hub. §3
removes the comment rather than carrying it forward.

## 2. Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 runbooks/plan-premises.py mqttx-web-v1.13.1     # all premises PASS; any FAIL = stop

# 2.1 target tag still resolves to the digest this plan reviewed (a re-push would void §1)
curl -s 'https://hub.docker.com/v2/repositories/emqx/mqttx-web/tags/v1.13.1' \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('digest'))"
# EXPECT: sha256:e777a2221a4e92ea0b87b3170a96ae09d4e557d2dc80c694175669762f47cfd0
# anything else (or None) = STOP, re-review.

# 2.2 flux healthy for this app
flux get kustomization -n home-automation mqttx-web
flux get helmrelease -n home-automation mqttx-web      # both Ready=True

# 2.3 prepare §4.2 — do NOT run it against the OLD pod: at 128Mi two back-to-back
#     app.js downloads OOMKilled it (2026-09-26T05:01:52Z), and a mid-transfer kill
#     would print FAIL 4.2 for the wrong reason. The negative control is already on
#     record: 2026-09-25 against v1.13.0 printed
#     "version_markers want=0 old=8 feature_markers=0" and "FAIL 4.2" (§4.2 baseline).
SCRATCH=$(mktemp -d); echo "$SCRATCH"   # write the §4.2 script to "$SCRATCH/mqttx-verify.sh"; carry the path by hand (shell state does not persist)
```

No backup is needed: nothing server-side is stateful (§1.2).

## 3. Steps

```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/home-automation/mqttx-web/app/helmrelease.yaml

# 3.1 bump the tag and drop the stale comment (BSD sed; dry-tested on a scratch copy 2026-09-25)
sed -i '' -E 's|^([[:space:]]*tag:) v1\.13\.0([[:space:]]+#.*)?$|\1 v1.13.1|' "$F"
# 3.1b the pod is OOMKilled at 128Mi serving its own 38 MB app.js (2026-09-25T01:55Z,
#      2026-09-26T05:01Z after two back-to-back §4.2 runs) — raise the limit
sed -i '' -E 's|^([[:space:]]*memory:) 128Mi$|\1 256Mi|' "$F"
git diff -- "$F"
# EXPECT one hunk, exactly two changed lines:
# -              tag: v1.13.0  # v1.13.3 is a GitHub release only; not published to Docker Hub (latest image tag is v1.13.0)
# +              tag: v1.13.1
# -                memory: 128Mi
# +                memory: 256Mi
grep -c 'tag: v1.13.1$' "$F"          # EXPECT 1
grep -c 'memory: 256Mi$' "$F"         # EXPECT 1

# 3.2 commit ONLY this path (shared worktree), verify, push
git commit --only "$F" -m "chore(mqttx-web): v1.13.0 -> v1.13.1, memory limit 128Mi -> 256Mi (plan mqttx-web-v1.13.1)"
git log -1 --format=%s                # must be THIS subject; amend before push if not
git show --stat HEAD                  # must list only the helmrelease
git push
```

Flux webhook reconciles; no manual `flux reconcile` needed (HR interval 30m —
if the webhook does not land within 5 min, `flux reconcile kustomization mqttx-web -n home-automation --with-source`
per `docs/sops/application-update.md`).

## 4. Verification

### 4.1 Rollout (floor, not the verdict)
```bash
kubectl -n home-automation get helmrelease mqttx-web -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'   # True
kubectl -n home-automation get deploy mqttx-web -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'              # emqx/mqttx-web:v1.13.1
kubectl -n home-automation get pods -l app.kubernetes.io/name=mqttx-web \
  -o jsonpath='{range .items[*]}{.metadata.name} {.status.phase} {.status.containerStatuses[0].imageID} restarts={.status.containerStatuses[0].restartCount} last={.status.containerStatuses[0].lastState.terminated.reason}{"\n"}{end}'
kubectl -n home-automation get deploy mqttx-web -o jsonpath='{.spec.template.spec.containers[0].resources.limits.memory}{"\n"}'   # 256Mi
# PASS: exactly one pod, Running, imageID contains e777a2221a4e, restarts=0, last= empty; limit 256Mi.
# FAIL shape it guards: rollout-status green on the OLD generation — imageID would still read 64525ad9…
```

### 4.2 CONTENTS — the served bundle is the new build and actually serves
Save as `$SCRATCH/mqttx-verify.sh` (runs under zsh or bash; tested under both
against the live v1.13.0 pod 2026-09-25):

```bash
WANT="${WANT:-1.13.1}"; OLD="${OLD:-1.13.0}"
T=$(mktemp -d); FAIL=0
kubectl -n home-automation port-forward svc/mqttx-web 18080:80 >/dev/null 2>&1 & PF=$!
sleep 3
curl -s -o "$T/index.html" -w 'index %{http_code} %{size_download}\n' http://127.0.0.1:18080/
grep -q -i 'id="app"' "$T/index.html" || { echo "FAIL index has no app mount"; FAIL=1; }
ASSETS=$(grep -o -i -E '(src|href)="/[^"]+\.(js|css)"' "$T/index.html" | sed -E 's/^[^"]*"\/?//; s/"$//' | sort -u)
N=$(printf '%s\n' "$ASSETS" | grep -c -v '^$')
echo "assets referenced: $N"
[ "$N" -ge 1 ] || { echo "FAIL no assets referenced"; FAIL=1; }
for f in $(printf '%s\n' "$ASSETS"); do
  code=$(curl -s -o "$T/a" -w '%{http_code}' "http://127.0.0.1:18080/$f")
  size=$(wc -c < "$T/a" | tr -d ' ')
  echo "$f code=$code size=$size"
  [ "$code" = 200 ] || { echo "FAIL $f code"; FAIL=1; }
  [ "$size" -gt 100000 ] || { echo "FAIL $f size<=100000"; FAIL=1; }
  head -c 64 "$T/a" | grep -q -i '<!doctype' && { echo "FAIL $f is HTML"; FAIL=1; }
  [ "$f" = app.js ] && cp "$T/a" "$T/app.js"
done
[ -s "$T/app.js" ] || { echo "FAIL app.js not referenced/fetched"; FAIL=1; }
NEW=$(grep -o -F "VUE_APP_VERSION\\\":\\\"$WANT" "$T/app.js" | wc -l | tr -d ' ')
STALE=$(grep -o -F "VUE_APP_VERSION\\\":\\\"$OLD" "$T/app.js" | wc -l | tr -d ' ')
FEAT=$(grep -o -F "showConnectionList" "$T/app.js" | wc -l | tr -d ' ')
echo "version_markers want=$NEW old=$STALE feature_markers=$FEAT"
[ "$NEW" -ge 1 ] || { echo "FAIL no $WANT marker"; FAIL=1; }
[ "$STALE" -eq 0 ] || { echo "FAIL $OLD marker still present"; FAIL=1; }
[ "$FEAT" -ge 1 ] || { echo "FAIL showConnectionList absent"; FAIL=1; }
kill $PF 2>/dev/null; wait $PF 2>/dev/null; rm -rf "$T"
[ "$FAIL" = 0 ] && echo "PASS 4.2" || echo "FAIL 4.2"
```

CONTENTS ASSERTION: the served app bundle is the v1.13.1 web build — measured by
the script above (`VUE_APP_VERSION":"1.13.1` ≥1, `1.13.0` markers = 0, and the
v1.13.1-only web feature string `showConnectionList` ≥1), every asset `index.html`
references returns 200, >100 kB, and is not an HTML fallback — compared to the
2026-09-25 baseline on v1.13.0: `index 200 2640`, `0.js 1088377 B`,
`app.js 38180243 B`, `version_markers want=0 old=8 feature_markers=0`.
**Can it fail?** Yes — run against the live v1.13.0 pod it prints `FAIL 4.2`
(three FAIL lines); a missing asset returns 404 from http-server (measured on
`/nope.js`), which trips the code check. PASS requires the literal `PASS 4.2`.

### 4.3 Through the real user path (envoy-internal)
```bash
H=$(kubectl -n home-automation get httproute mqttx-web -o jsonpath='{.spec.hostnames[0]}')
kubectl -n home-automation get httproute mqttx-web -o jsonpath='{.status.parents[0].conditions[?(@.type=="Accepted")].status}{"\n"}'   # True
curl -s -o /dev/null -w '%{http_code}\n' --resolve "$H:443:192.168.55.103" "https://$H/"                                        # 200
curl -s --resolve "$H:443:192.168.55.103" "https://$H/app.js" | grep -o -F 'VUE_APP_VERSION\":\"1.13.1' | wc -l | tr -d ' '   # >=1
```
PASS: Accepted=True, 200, marker count ≥1. Baseline 2026-09-25 (old build): 200
and a `1.13.0` count of 8 on this path, i.e. the grep measures real content, and
it returns 0 for `1.13.1` today (would FAIL).

### 4.3b No OOM under the verification load
Re-run the §4.1 pod line after §4.3. PASS: `restarts=0` and `last=` empty. It can fail: on 2026-09-26 the same line read `restarts=2 last=OOMKilled` against v1.13.0 at 128Mi. If this FAILS at 256Mi: STOP and surface to the operator. Do NOT revert, because a revert restores 128Mi; the forward fix is raising the limit to 512Mi.

### 4.4 Prometheus controls (after ≥5 min settle)
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
for q in 'kube_deployment_status_replicas_available{namespace="home-automation",deployment="mqttx-web"}' \
         'max(kube_pod_container_status_restarts_total{namespace="home-automation",container="app",pod=~"mqttx-web-.*"})'; do
  curl -s --get http://127.0.0.1:19090/api/v1/query --data-urlencode "query=$q" \
  | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print(len(r), [x['value'][1] for x in r])"
done
kill $PF 2>/dev/null
```
CONTROL: metric kube_deployment_status_replicas_available — exactly ONE series with value `1`. An empty result is FAIL, not pass: the negative control (`deployment="mqttx-web-nonexistent"`) returned `0 []` on 2026-09-25; baseline for the real deployment `1 ['1']`.
CONTROL: metric kube_pod_container_status_restarts_total — exactly one result, value `0` (the new pod has not restarted). Baseline `1 ['0']` (2026-09-25). Non-zero demonstrated: the old pod read restartCount 2 (OOMKilled) on 2026-09-26.

## 5. Rollback

Stateless, so a revert is the whole procedure:

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha-of-3.2>          # restores `tag: v1.13.0` (and the stale comment)
git log -1 --format=%s                      # confirm it is YOUR revert subject
git show --stat HEAD                        # only the mqttx-web helmrelease
git push
```
Confirm: `kubectl -n home-automation get deploy mqttx-web -o jsonpath='{.spec.template.spec.containers[0].image}'`
→ `emqx/mqttx-web:v1.13.0`; pod imageID contains `64525ad96286`; §4.2 run with
`WANT=1.13.0 OLD=1.13.1` shows `want=8 old=0` (the `showConnectionList` line will
FAIL on the old build — expected, ignore that one line on rollback).
Browser-side: users who loaded v1.13.1 keep a `settings.showConnectionList` key in
their localStorage; v1.13.0 never reads it, so no clean-up is needed.

## 6. Interference notes

- Leaf app: nothing else in `home-automation` or cluster-wide consumes it; the
  Service/HTTPRoute objects are not modified, so envoy-internal routing for other
  hosts is unaffected. A ~30 s outage of the MQTTX web UI only (Recreate).
- `conflicts_with`: `kube-prometheus-stack-91.4.1` because §4.4 reads Prometheus;
  `talos-1.14.1` because a node roll reschedules the pod and blinds KSM mid-gate.
  Neither plan names this one yet — the scheduler honours the field symmetrically.
- `capability_change: true` routes this to an attended execution class. If the
  operator judges the additive UI features non-material, reclassifying is a
  one-field edit; the risk analysis above does not change.
- Suggested follow-up (repo correction, not done here): the G3 structural signal
  in `auto-update.py structural_signal()` / `coverage.py structural_change_signal()`
  scans the whole upstream monorepo diff. For monorepos whose image is built from a
  sub-path (here `context: ./web`), migrations outside that build context should not
  hold the image. Until that is scoped, every MQTTX release that touches desktop
  migrations will re-hold `mqttx-web`.
