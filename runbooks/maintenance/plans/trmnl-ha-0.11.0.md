---
plan_id: trmnl-ha-0.11.0
component: trmnl-ha
pr: null                              # no Renovate PR; surfaced by coverage.py (lane=PLAN) and
                                      # dispatched by the nightly window 2026-09-29 Step 0.5.
kind: image
current: "0.10.3"                     # live 2026-09-29: deploy image ghcr.io/usetrmnl/trmnl-ha-amd64:0.10.3,
                                      # pod imageID ...@sha256:042034fef5d91140d2d1e8cac43697e9496f07fa86d6137daedbfd2774c11107
                                      # (= ghcr manifest digest of tag 0.10.3, read the same day).
target: "0.11.0"                      # tag EXISTS: ghcr HEAD manifests/0.11.0 -> HTTP 200,
                                      # application/vnd.oci.image.manifest.v1+json,
                                      # docker-content-digest sha256:c7b4027372264eb5faee88eac45ce257218f6dd146f1337dc66c25fd6b775b28
                                      # (single-arch manifest, not an index). Upstream release v0.11.0
                                      # published 2026-09-28T20:04Z (usetrmnl/trmnl-home-assistant).
update_type: minor
risk: low                             # hold is the generic 0.x-minor rule, not a breaking-change signal.
                                      # §1: 9 upstream commits, 4 of them the separate Terminus add-on
                                      # (not our image); the rest are opt-in schedule options + two
                                      # render fixes. No route, storage-format, env or port change.
est_duration_min: 20                  # pre-checks 4 + edit/commit/push/Flux ~4 + Recreate/pull ~3
                                      # + gates G1-G6 ~5 + G7 settle 10 min is waited, not worked (slack 4)
needs_reboot: false
touches:
  namespaces: [home-automation]
  resources:
    - helmrelease/trmnl-ha            # the edit (kubernetes/apps/home-automation/trmnl-ha/app/helmrelease.yaml, image tag only)
    - deployment/trmnl-ha             # strategy Recreate (live), 1 replica -> one pod replaced
    - pvc/trmnl-ha-data               # longhorn (dynamic) RWO 1Gi, PV pvc-e230506d-..., reclaim Delete;
                                      # REMOUNTED only. No PVC/PV action of any kind in this plan.
    - service/trmnl-ha                # unchanged; endpoints move to the new pod
    - httproute/trmnl-ha              # unchanged; UI unavailable ~1 min during Recreate
  shared: [monitoring]                # instrument only: G7 reads kube-state-metrics through Prometheus.
                                      # trmnl-ha is a READ client of home-assistant (HTTP, token) and an
                                      # egress client of the TRMNL cloud webhook; neither is perturbed.
depends_on: []
conflicts_with:
  - app-template-5.2.1                # its Batch A bumps the chart in THIS helmrelease.yaml (trmnl-ha is one of
                                      # the 78 5.1.0 consumers; version finding F-8016b6d3). Either order works,
                                      # not the same window: G1-G7 attribute a failure to the image.
  - helm-drift-detection              # adds spec.driftDetection to every HR incl. this one (same object,
                                      # same helm-controller upgrade).
  - flux-oci-chart-sources            # rewrites spec.chart of app-template HRs incl. this one.
  - flux-reconciler-impersonation     # exclusive:true already keeps its slot empty; named because this plan's
                                      # delivery path IS the Flux apply that plan re-identities.
  - flux-fleet-0.60.0                 # helm-controller upgrade = this plan's delivery path; not the same night
                                      # (plan review 2026-09-29).
exclusive: false
security_ref: F-2b739b70              # open accepted image finding on 0.10.3 (AR-059); 0.11.0 is the first newer
                                      # upstream tag and is a full base rebuild (plan review 2026-09-29, trivy-measured;
                                      # counts kept out of the repo).
capability_change: false              # 0.11.0 adds two OPT-IN schedule fields (crop_fit, timestampPosition);
                                      # both default off/absent and our only schedule sets neither
                                      # (live /data/schedules.json read 2026-09-29). http-router.ts is NOT in the
                                      # 0.10.3...0.11.0 diff -> no new route/API. TIMESTAMP_OVERLAY env is unset,
                                      # so the stamp resize change is dormant. No permission/exposure change.
rollback_class: git-revert            # nothing forward-only: no schema/migration; scheduleStore is not in the
                                      # diff; schedules.json is rewritten only on a UI save, and the only new
                                      # keys are optional fields 0.10.3 ignores. §2 takes a local copy anyway.
finding_refs: [F-f1c20bc7, F-2b739b70, F-abfb145e] # F-f1c20bc7 = the version finding for this bump; the other two
                                      # are open against the 0.10.3 image (AR-059 / AR-029); this bump is their remedy. F-8016b6d3 is the CHART 5.1.0->5.2.1 finding, owned by
                                      # app-template-5.2.1, not this plan.
review: ready-for-go@2026-09-29
status: vetted
window: null
premises:
  - id: image-is-still-0.10.3
    why: >-
      `current:` and the G1/G4 baselines (digest 042034fe, 723x394 1-bit
      render at 2.43% black) were captured against this exact pin. If the
      Deployment already moved, this plan is stale.
    run: kubectl get deploy -n home-automation trmnl-ha -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/usetrmnl/trmnl-ha-amd64:0.10.3
  - id: repo-pin-is-0.10.3
    why: "Step 3.1's sed anchors on this exact line; zero or two matches means the file moved under the plan."
    run: >-
      grep -c '^[[:space:]]*tag: 0\.10\.3$' kubernetes/apps/home-automation/trmnl-ha/app/helmrelease.yaml
    expect_exact: "1"
  - id: hr-ready
    why: "A HelmRelease already failing would mask whether the bump itself reconciled."
    run: kubectl get helmrelease -n home-automation trmnl-ha -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: strategy-recreate
    why: >-
      Single replica on an RWO Longhorn PVC: a RollingUpdate would schedule the
      new pod before the old one detaches and can block on Multi-Attach
      (docs/sops/longhorn-rwo-multi-attach.md). Live value 2026-09-29 is Recreate.
    run: kubectl get deploy -n home-automation trmnl-ha -o jsonpath='{.spec.strategy.type}'
    expect_exact: Recreate
  - id: last-scheduled-run-delivered
    why: >-
      The hourly "Energy Dashboard" schedule (cron 10 * * * *, UTC) must be
      delivering BEFORE the change, or G5 cannot attribute a failure to the
      image. grep -c prints 0 (and the premise fails) if no successful
      delivery was logged in the last 2h.
    run: >-
      kubectl logs -n home-automation deploy/trmnl-ha --since=2h | grep -ci 'webhook success: 200'
    expect_matches: "^[1-9][0-9]*$"
  - id: data-volume-healthy
    why: "Longhorn backup of the data volume is the backstop behind the §2 local copy; it must be attached and healthy."
    run: kubectl get volumes.longhorn.io -n storage pvc-e230506d-5f62-41cd-88b0-7ddcab0e90d8 -o jsonpath='{.status.state}/{.status.robustness}'
    expect_exact: attached/healthy
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-09-29"
---

# trmnl-ha 0.10.3 -> 0.11.0

## 1. Summary & why held

`trmnl-ha` renders a Home Assistant dashboard (`/dashboard-controls/energy-trmnl`)
in headless Chromium once an hour, dithers it to a 1-bit PNG and pushes it to the
TRMNL cloud webhook for the e-ink display. Single Deployment (app-template 5.1.0),
`Recreate`, 1Gi Longhorn RWO PVC at `/data` holding `schedules.json` + `output/`.
HTTPRoute on `envoy-internal` (LAN only) for the config UI.

**Why held:** coverage.py's generic rule — "0.x release-line move (0.10 -> 0.11) —
at major 0 the minor IS the breaking axis". There is **no breaking-change signal
upstream**; this is a false-positive-shaped hold and the plan is `risk: low`.

**Upstream evidence** (release `v0.11.0`, `usetrmnl/trmnl-home-assistant`, and the
`v0.10.3...v0.11.0` compare — 9 commits):

> ### Added
> - A "Fit crop to viewport" option that scales a cropped capture up to the screen
>   size, padded with white ... (#118)
> - A choice of corner for the capture time, and the stamp now grows on wider
>   screens so it stays readable (#119)
>
> ### Fixed
> - Clocks showed 12-hour time and numbers used US decimals when a Home Assistant
>   profile was set to "Use system locale", because the add-on's browser always
>   reports US English. They now follow the user's language (#122, #123)
> - Picking a device preset lost its PNG bit depth when the schedule was saved ... (#118)
> - Clearing a device preset kept the old device and its bit depth on the schedule (#124)

What each means for OUR deployment (read from the diff, not the notes):

| Change | Code path | Effect here |
|---|---|---|
| crop_fit (#118) | `params-builder.ts`: `cropFit: schedule.crop_fit ?? false`; `screenshot.ts` applies `fitToViewport` only when `cropFit && hasCrop` | Our schedule has crop enabled but **no `crop_fit` key** -> false -> output stays 723x394 (baseline). |
| timestamp corner + size (#119) | `dithering.ts annotateTimestamp` only runs when `timestamp || TIMESTAMP_OVERLAY` | Schedule has no `timestamp`; env `TIMESTAMP_OVERLAY` unset (pod env: TZ, HOME_ASSISTANT_URL, KEEP_BROWSER_OPEN + secret key ACCESS_TOKEN only). Dormant. |
| locale fix (#122/#123) | `page-setup-strategies.ts` switches HA `time/number/date_format` from `system` to `language` in the page | Possible **cosmetic** change on the e-ink image (clock/number formatting follows `lang: en` instead of browser en-US). Not a failure; G4 bands tolerate it. |
| preset bit-depth fixes | UI (`app.ts`, `device-presets.ts`) | Only on UI save; we don't use presets. G4 still asserts depth 1. |
| 4x "Updated Terminus" | `trmnl-terminus/*` | Separate add-on, not in this image. |

Not in the diff: `http-router.ts`, `scheduleStore.ts`, `main.ts`, any Dockerfile /
run script / `config.yaml` beyond the version string -> no route, storage-format,
port (10000), `/data` path or env contract change.

## 2. Pre-checks

Run from the repo root on the Mac mini (zsh). Premises in frontmatter must all PASS first:

```bash
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 runbooks/plan-premises.py trmnl-ha-0.11.0
```

2.1 Flux + HA healthy (trmnl-ha renders HA; if Step 0 of this window rolled
home-assistant, wait until it is Ready before continuing):

```bash
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
kubectl get helmrelease -n home-automation trmnl-ha home-assistant
kubectl get deploy -n home-automation home-assistant -o jsonpath='{.status.readyReplicas}/{.spec.replicas}{"\n"}'   # expect 1/1
```

2.2 Timing: the schedule fires at **hh:10 UTC** (plus up to ~20s jitter). Do not
push Step 3 between hh:07 and hh:13 UTC — a Recreate mid-run just skips that
hour's image, but it would confuse G5. `date -u +%H:%M`.

2.3 Local copy of the app state (read-only `exec cat`; this is the rollback
source for `schedules.json`, which has no GitOps path — it is UI-written state on the PVC):

```bash
TS=$(date +%Y%m%d_%H%M%S)
kubectl exec -n home-automation deploy/trmnl-ha -- cat /data/schedules.json > /tmp/trmnl-schedules.backup.$TS.json
kubectl exec -n home-automation deploy/trmnl-ha -- md5sum /data/schedules.json | cut -d' ' -f1 | tee /tmp/trmnl-schedules.md5
md5 -q /tmp/trmnl-schedules.backup.$TS.json          # must equal the line above
echo /tmp/trmnl-schedules.backup.$TS.json             # note this path for §5
```

2.4 Backstop freshness: `kubectl get volumes.longhorn.io -n storage pvc-e230506d-5f62-41cd-88b0-7ddcab0e90d8 -o jsonpath='{.status.lastBackupAt}{"\n"}'`
should be within ~26h (was 2026-09-28T03:04Z at authoring). Stale is NOT a blocker
(2.3 is the primary copy) — record it.

2.5 Install the render checker used by G4 (pure python, no deps; decodes the 1-bit
PNG and prints dims/depth/black%):

```bash
cat > /tmp/pngstat.py <<'EOF'
import sys, zlib, struct
b = open(sys.argv[1], 'rb').read()
assert b[:8] == b'\x89PNG\r\n\x1a\n', 'NOT_PNG'
pos, idat, ihdr = 8, b'', None
while pos < len(b):
    n, = struct.unpack('>I', b[pos:pos+4]); t = b[pos+4:pos+8]; d = b[pos+8:pos+8+n]
    if t == b'IHDR': ihdr = struct.unpack('>IIBBBBB', d)
    if t == b'IDAT': idat += d
    pos += 12 + n
w, h, depth, ctype = ihdr[:4]
assert depth == 1 and ctype == 0, f'UNEXPECTED depth={depth} ctype={ctype}'
raw = zlib.decompress(idat); stride = (w + 7) // 8
prev = bytearray(stride); black = 0
for y in range(h):
    f = raw[y*(stride+1)]; line = bytearray(raw[y*(stride+1)+1:(y+1)*(stride+1)])
    for i in range(stride):
        a = line[i-1] if i else 0; up = prev[i]; c = prev[i-1] if i else 0
        if f == 1: line[i] = (line[i] + a) & 255
        elif f == 2: line[i] = (line[i] + up) & 255
        elif f == 3: line[i] = (line[i] + ((a + up) >> 1)) & 255
        elif f == 4:
            p = a + up - c; pa, pb, pc = abs(p-a), abs(p-up), abs(p-c)
            line[i] = (line[i] + (a if pa <= pb and pa <= pc else up if pb <= pc else c)) & 255
    for x in range(w):
        if not (line[x//8] >> (7 - x % 8)) & 1: black += 1
    prev = line
pct = 100*black/(w*h)
ok = (w, h, depth) == (723, 394, 1) and 0.5 <= pct <= 10.0
print(f'dims={w}x{h} depth={depth} bytes={len(b)} black_pct={pct:.2f} -> {"PASS" if ok else "FAIL"}')
sys.exit(0 if ok else 1)
EOF
```

2.6 Pre-change render baseline (same command as G4, run now against 0.10.3):

```bash
kubectl port-forward -n home-automation svc/trmnl-ha 11000:10000 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s -o /tmp/trmnl-pre.png -w 'HTTP=%{http_code} CT=%{content_type} BYTES=%{size_download}\n' --max-time 90 \
  'http://localhost:11000/dashboard-controls/energy-trmnl?viewport=800x480&crop_x=41&crop_y=86&crop_width=723&crop_height=394&dithering&dither_method=ordered&palette=bw&lang=en'
kill $PF 2>/dev/null
python3 /tmp/pngstat.py /tmp/trmnl-pre.png
```

Measured at authoring (2026-09-29 01:48Z, 0.10.3): `HTTP=200 CT=image/png BYTES=2107`,
`dims=723x394 depth=1 bytes=2107 black_pct=2.43`. If the pre-change run already FAILs, stop — the problem predates this plan.

## 3. Steps

3.1 Edit the tag (dry-tested on a scratch copy with BSD sed 2026-09-29; resulting diff was exactly
`33c33 <               tag: 0.10.3 --- >               tag: 0.11.0`):

```bash
cd /Users/mu/code/cberg-home-nextgen
sed -i '' 's/^\([[:space:]]*tag:\) 0\.10\.3$/\1 0.11.0/' kubernetes/apps/home-automation/trmnl-ha/app/helmrelease.yaml
git diff --stat kubernetes/apps/home-automation/trmnl-ha/app/helmrelease.yaml    # 1 file, 1 insertion, 1 deletion
grep -c '^[[:space:]]*tag: 0\.11\.0$' kubernetes/apps/home-automation/trmnl-ha/app/helmrelease.yaml   # must print 1
```

3.2 Commit ONLY this path (shared worktree), verify ownership, push:

```bash
cat > /tmp/trmnl-msg.txt <<'EOF'
chore(trmnl-ha): bump image 0.10.3 -> 0.11.0 (plan trmnl-ha-0.11.0)

Opt-in crop_fit/timestamp-corner options + locale and preset bit-depth fixes.
No route/storage/env change upstream; held only by the 0.x-minor rule.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
git commit --only kubernetes/apps/home-automation/trmnl-ha/app/helmrelease.yaml -F /tmp/trmnl-msg.txt
git log -1 --format=%s            # must be "chore(trmnl-ha): bump image 0.10.3 -> 0.11.0 ..."; amend before push if not
git show --stat HEAD              # exactly one file: .../trmnl-ha/app/helmrelease.yaml
git push
```

3.3 Let the webhook reconcile (no manual `flux reconcile` by default). If the HR has
not picked up the new revision within 5 min, the SOP permits
`flux reconcile kustomization trmnl-ha -n home-automation --with-source` (the live Kustomization is in `home-automation`: the parent's targetNamespace overrides ks.yaml's flux-system; `-n flux-system` returns NotFound, verified 2026-09-29).

## 4. Verification

Record the rollout time: `T0=$(date -u +%Y-%m-%dT%H:%M:%SZ)` immediately BEFORE the §3 push (G3 also compares against the new pod's `.status.startTime`).

**G1 — the new image, by digest, is what runs.**
```bash
kubectl get pod -n home-automation -l app.kubernetes.io/name=trmnl-ha \
  -o jsonpath='{range .items[*]}{.metadata.name} {.status.phase} {.status.containerStatuses[0].imageID} restarts={.status.containerStatuses[0].restartCount}{"\n"}{end}'
```
PASS: exactly ONE pod, `Running`, imageID ends `@sha256:c7b4027372264eb5faee88eac45ce257218f6dd146f1337dc66c25fd6b775b28`, restarts=0.
Guards against: rollout status green-lighting the old generation (imageID would still read `042034fe…`); a second pod stuck on Multi-Attach (two lines).

**G2 — HelmRelease reconciled on the unchanged chart.**
```bash
kubectl get helmrelease -n home-automation trmnl-ha -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion} {.status.history[0].status}{"\n"}'
```
PASS: `True 5.1.0 deployed`. A failed upgrade prints `False` (and the HR's `remediation: rollback` would put 0.10.3 back — G1 then fails on the digest).

**G3 — browser health endpoint (floor, not the gate).**
```bash
kubectl port-forward -n home-automation svc/trmnl-ha 11000:10000 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s -w '\nHTTP=%{http_code}\n' http://localhost:11000/health | python3 -c "
import sys; raw=sys.stdin.read(); body,code=raw.rsplit('HTTP=',1); import json; d=json.loads(body)
b=d['browser']; print('status',d['status'],'healthy',b['healthy'],'fail',b['consecutiveFailures'],'last',b['lastSuccessfulRequest'],'HTTP',code.strip())"
```
PASS: `status ok healthy True fail 0 HTTP 200`. Fail shape: `degraded`/HTTP 503 (router returns 503 when `checkHealth().healthy` is false). Note: on a fresh pod `lastSuccessfulRequest` equals process start (browserFacade `#lastSuccess = Date.now()` at construction, verified in upstream v0.11.0 source), so healthy is trivially true — that is why G4 exists. Record `$T0` BEFORE the push (or compare against the new pod's `.status.startTime`), re-run G3 after G4, and require `last` to be later than both.

**G4 — CONTENTS: the dashboard actually renders to a 1-bit e-ink image.** (read-only GET, no webhook, same params as our schedule; keep the G3 port-forward)
```bash
curl -s -o /tmp/trmnl-post.png -w 'HTTP=%{http_code} CT=%{content_type} BYTES=%{size_download}\n' --max-time 90 \
  'http://localhost:11000/dashboard-controls/energy-trmnl?viewport=800x480&crop_x=41&crop_y=86&crop_width=723&crop_height=394&dithering&dither_method=ordered&palette=bw&lang=en'
python3 /tmp/pngstat.py /tmp/trmnl-post.png; echo "exit=$?"
```
CONTENTS ASSERTION: the rendered Energy dashboard is a 723x394 1-bit PNG with 0.5–10 % black pixels — measured by `/tmp/pngstat.py`, compared to the §2.6 baseline (authoring: 2.43 %, 2107 bytes).
PASS: `HTTP=200 CT=image/png`, pngstat prints `-> PASS`, `exit=0`.
It can fail, measured: a path HA doesn't serve returned `HTTP=404 BYTES=130` (JSON) and pngstat aborts `NOT_PNG` (negative control run 2026-09-29 against 0.10.3); a bit-depth regression (the #118 code area) aborts `UNEXPECTED depth=`; an accidental crop_fit or wrong crop fails the dims check; a blank/white page (HA unreachable, token rejected, frontend not loaded) reads black_pct < 0.5 -> FAIL. Limitation stated honestly: a login-page render was not measured, so G5's log line is the auth cross-check.

**G5 — CONTENTS: the real delivery path (scheduler -> render -> TRMNL webhook) works.** Either wait for the next hh:10 UTC run, or trigger it now (identical to the hourly cron: pushes one fresh image to the display). Do not print the webhook URL (it carries the plugin id).
```bash
SID=$(curl -s http://localhost:11000/api/schedules | python3 -c "import sys,json; print([s['id'] for s in json.load(sys.stdin) if s['name']=='Energy Dashboard'][0])")
curl -s -X POST --max-time 120 "http://localhost:11000/api/schedules/$SID/send" | python3 -c "
import sys,json; r=json.load(sys.stdin); w=r.get('webhook') or {}
print('success',r.get('success'),'webhook_success',w.get('success'),'status',w.get('statusCode'),'error',w.get('error'))"
kill $PF 2>/dev/null
kubectl logs -n home-automation deploy/trmnl-ha --since-time="$T0" | grep -iE 'Completed: Energy Dashboard|webhook failed|error' | sed -E 's#https://[^ ]+#<url>#g'
```
CONTENTS ASSERTION: a post-upgrade run of the real schedule reports webhook HTTP 200 from the TRMNL cloud — measured by the `/send` result and the `Completed: Energy Dashboard ... webhook: 200 OK` log line after `$T0`.
PASS: `success True webhook_success True status 200 error None`, and at least one `Completed: Energy Dashboard … webhook: 200 OK` line after `$T0`, and no `webhook failed` line. Fail shapes from the code (`schedule-executor.ts`): `webhook: FAILED (<error>)`, log `webhook failed: …`, or a 500 `{"error": …}` from `/send`. Then re-run G3 and require `last` > `$T0`.

**G6 — app state untouched.**
```bash
kubectl exec -n home-automation deploy/trmnl-ha -- md5sum /data/schedules.json | cut -d' ' -f1 | diff - /tmp/trmnl-schedules.md5 && echo SCHEDULES_UNCHANGED
```
PASS: `SCHEDULES_UNCHANGED`. `scheduleStore.ts` is not in the upstream diff and our webhook is not BYOS (the only code path that writes schedule updates during a run), so any change means something unexpected rewrote the file — compare against the §2.3 copy before deciding.

**G7 — settle (+10 min after `$T0`), via Prometheus.**
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PP=$!; sleep 3
for q in 'kube_deployment_status_replicas_available{namespace="home-automation",deployment="trmnl-ha"}' \
         'sum(kube_pod_container_status_restarts_total{namespace="home-automation",pod=~"trmnl-ha-.*"})'; do
  curl -s -G http://localhost:19090/api/v1/query --data-urlencode "query=$q" | python3 -c "
import sys,json; r=json.load(sys.stdin)['data']['result']; print('EMPTY' if not r else r[0]['value'][1])"
done; kill $PP 2>/dev/null
```
CONTROL: metric kube_deployment_status_replicas_available — must read `1` (not `0`, not `EMPTY`; series confirmed present and =1 at authoring).
CONTROL: metric kube_pod_container_status_restarts_total — summed over trmnl-ha pods must read `0` (confirmed present, 0 at authoring). `EMPTY` on either is a FAIL, not a pass: the pod selector matched nothing.
trmnl-ha exposes no scrape target (`up{namespace="home-automation",service="trmnl-ha"}` is empty), so app-level truth comes from G4/G5, not Prometheus.

**G8 — security bookkeeping (post-window, next sweep).** The sweep's security-check re-scans the deployed `ghcr.io/usetrmnl/trmnl-ha-amd64:0.11.0`. Confirm F-2b739b70 / F-abfb145e resolve on the old tag, then re-evaluate AR-059 and AR-029 with `runbooks/policy-cli.py risk` — their "already the newest tag" / "no upstream fix" premises are false once 0.11.0 is deployed; renew or disable it consciously, never silently.

## 5. Rollback

Trigger: any of G1–G7 FAIL that is not explained by HA itself being down (check 2.1 again first).

1. Revert the bump (git-only; nothing forward-only happened):
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   git revert --no-edit <sha-of-3.2>
   git log -1 --format=%s        # must be: Revert "chore(trmnl-ha): bump image 0.10.3 -> 0.11.0 ..."
   git show --stat HEAD          # only trmnl-ha/app/helmrelease.yaml
   git push
   ```
   If the HR is wedged `pending-upgrade`, follow `docs/sops/application-update.md` §11 before re-pushing.
2. Confirm the cluster is back: G1 must show imageID `@sha256:042034fef5d91140d2d1e8cac43697e9496f07fa86d6137daedbfd2774c11107`, restarts 0; G2 `True 5.1.0 deployed`; re-run G4 -> `PASS`.
3. Only if G6 failed (schedules.json changed): restore the §2.3 copy. This is UI state on the PVC with no GitOps path (CLAUDE.md in-pod exception applies — back up first, write, read back):
   ```bash
   B=/tmp/trmnl-schedules.backup.<TS>.json          # path printed in §2.3
   kubectl exec -n home-automation deploy/trmnl-ha -- sh -c 'cp /data/schedules.json /data/schedules.json.backup.$(date +%Y%m%d_%H%M%S)'
   kubectl exec -i -n home-automation deploy/trmnl-ha -- sh -c 'cat > /data/schedules.json' < "$B"
   kubectl exec -n home-automation deploy/trmnl-ha -- md5sum /data/schedules.json | cut -d' ' -f1 | diff - /tmp/trmnl-schedules.md5 && echo RESTORED
   ```
   Then restart nothing — `scheduler.ts` hot-reloads the schedule file every 60 s (upstream header comment, v0.11.0); wait 60 s and confirm with G5.
   Backstop if the local copy is lost: Longhorn backup of `pvc-e230506d-5f62-41cd-88b0-7ddcab0e90d8` (restore per `docs/sops/backup.md`). The PV is reclaim `Delete` — never delete the PVC as part of a rollback.

## 6. Interference notes

- Serialize with **app-template-5.2.1** (nightly 2026-10-02 at authoring): it edits the same `helmrelease.yaml` (chart line). Either order is fine; one window each so a failure is attributable. Reciprocal `conflicts_with` added to that plan (review 2026-09-29).
- **flux-fleet-0.60.0** (nightly 2026-10-06): helm-controller upgrade = this plan's delivery path; not the same night.
- helm-drift-detection / flux-oci-chart-sources / flux-reconciler-impersonation: same HelmRelease object / same delivery path — listed in `conflicts_with`.
- Depends at runtime on **home-assistant** (render target). Step 0 safe updates frequently bump HA in the same nightly window (e.g. 2026.9.3 -> 2026.9.4 tonight); run this plan only after HA is Ready, otherwise G4/G5 fail for a reason that is not this image.
- No `kube-prometheus-stack` plan is open; G7 reads kube-state-metrics — if one appears on the same night, add it to `conflicts_with`.
- The hourly schedule at hh:10 UTC is the one thing to avoid (§2.2). Nightly window 03:30 Europe/Berlin = 01:30 UTC, so the natural slot is 01:30–02:07 UTC.
- Downtime: the config UI (LAN-only HTTPRoute) is unavailable ~1 min during the Recreate; the e-ink display just keeps its last image. No other app shares the pod, PVC or Service.
