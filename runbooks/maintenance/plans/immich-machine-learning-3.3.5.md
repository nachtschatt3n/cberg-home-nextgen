---
plan_id: immich-machine-learning-3.3.5
component: immich-machine-learning
pr: 360                               # Renovate PR #360 (immich monorepo v3.3.3 -> v3.3.5, moves server+ML) is OPEN (verified 2026-10-22; #282 postgres, #240 redis also open).
                                      # RISK: if #360 merges outside this plan, the lane could land the SERVER bump without the backup gate.
                                      # runbooks/auto-update-policy.yaml has NO immich deny rule (grep-verified). Only holds: coverage/G3 (unverified notes +
                                      # structural migration-file signal) and earned autonomy (2 green/0 revert vs 3 needed). Repo correction owed: add an immich-server deny rule.
kind: image
current: "v3.3.3-openvino"
target: "v3.3.5-openvino"             # Verified 2026-10-22: ghcr.io/immich-app/immich-machine-learning:v3.3.5-openvino ->
                                      # OCI index sha256:1dbac7f811b51b80c55ee0cf678e0089d3532c798f14a65747d5d7b473a4f9d6
                                      # (HTTP 200). Plain CPU fallback v3.3.5 also exists (sha256:5b28c935...). GitHub
                                      # release v3.3.5 published 2026-10-21T18:12Z, newest release.
update_type: security
risk: low                             # §1: the ML side of 3.3.3 -> 3.3.5 is base-image digests + one Python dependency +
                                      # the version string; zero ML source change, no onnxruntime/OpenVINO version change,
                                      # no DB (ML is stateless), cache PVC untouched. The hold was a G3 "notes unverified"
                                      # signal, not a breaking-change signal -- notes are now read (§1.2).
est_duration_min: 20                  # ~3 min Recreate + pull of a large OpenVINO image on nuc14-01, ~10 min verification,
                                      # +5 buffer. The trivy re-scan in §4.6 runs on the Mac and is the long pole.
needs_reboot: false
touches:
  namespaces: [media]
  resources:
    - helmrelease/immich-machine-learning
    - deployment/immich-machine-learning   # Recreate: ~1-3 min with no ML backend; server keeps serving the library
    - pvc/immich-ml-cache                  # re-mounted (RWO Longhorn), not written by the change; models are reused
  shared:
    - igpu-i915                       # the replacement pod re-requests gpu.intel.com/i915 on its node (5 slots/node,
                                      # nuc14-01 currently uses 4: immich-ml, immich-server, jellyfin, makemkv)
    - monitoring                      # READ-only: §2/§4 read Prometheus (kube_pod_status_ready, ImmichMLNotReady)
depends_on: []                        # NOT coupled to immich-server-3.3.5 -- see §6. The server->ML contract is
                                      # GET /ping + POST /predict with no version check (server
                                      # src/repositories/machine-learning.repository.ts @ v3.3.5, lines 133/171), the ML
                                      # code is identical across 3.3.3..3.3.5, and the 3.3.4 DB migration is server-only.
conflicts_with:
  - kube-prometheus-stack-92.11.0     # same instrument (symmetric)
  - jellyfin-12.2.20261005            # i915 claimant on the same node
  - jellyfin-config-rwo-migration     # i915 claimant in media
  - node-feature-discovery-0.20.0     # a dropped GPU label leaves the restarted i915 pod Pending
  - helm-drift-detection              # rolls the intel-gpu-plugin DaemonSet / changes HR apply
  - kube-prometheus-stack-92.10.1     # draft, exclusive; §2/§4 read Prometheus (the window's instrument)
  - kube-prometheus-stack-92.2.0      # draft; same instrument
exclusive: false
security_ref: F-611ca4c7              # security driver; detail (incl. what 3.3.5 does and does NOT clear) stays on the record
capability_change: false              # same-behaviour patch: no ML code change, same models, same API, same execution
                                      # providers; only base layers and a CA-bundle dependency move
rollback_class: git-revert            # nothing forward-only: ML holds no DB, the /cache models are version-independent
                                      # (same ViT-B-32__openai / buffalo_l / LATIN__PP-OCRv5_mobile files are reused)
finding_refs: [F-611ca4c7, F-6d0f4efc] # F-611ca4c7 = security finding (v3.3.3-openvino); F-6d0f4efc = version finding
                                      # for this image (immich-machine-learning v3.3.3-openvino -> newer, monitor)
review: ready-for-go@2026-10-22   # plan-reviewer 2026-10-22: needs-fix (PR #360 comment, conflicts, order) -> fixed; no DB; git-revert rollback; premises 5/5
status: executed
window: "now:2026-10-22"   # ON-DEMAND NOW run 2026-10-22 (run-now.py stamp; was None)
premises:
  - id: ml-image-is-still-v3.3.3-openvino
    why: >-
      current: and the rollback target are v3.3.3-openvino. If the image moved
      (a coverage direct-bump, a manual swap to the CPU tag), the diff, the
      baselines and the rollback are wrong.
    run: kubectl get deploy -n media immich-machine-learning -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/immich-app/immich-machine-learning:v3.3.3-openvino
  - id: ml-strategy-recreate
    why: >-
      Single replica on an RWO Longhorn PVC (immich-ml-cache). RollingUpdate
      would risk a Multi-Attach hang (docs/sops/longhorn-rwo-multi-attach.md).
    run: kubectl get deploy -n media immich-machine-learning -o jsonpath='{.spec.strategy.type}'
    expect_exact: Recreate
  - id: ml-helmrelease-chart-5.3.0
    why: >-
      Verification assumes the app-template 5.3.0 render (container `main`,
      tcpSocket probes on 3003). Any other chart means an unreviewed render change.
    run: kubectl get helmrelease -n media immich-machine-learning -o jsonpath='{.status.history[0].chartVersion}'
    expect_exact: 5.3.0
  - id: server-still-on-3.3-line
    why: >-
      The no-coupling claim (§6) was checked for a 3.3.x server against a 3.3.5
      ML. A server outside the 3.3 line voids it and forces a re-read.
    run: kubectl get deploy -n media immich-server -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_matches: 'ghcr\.io/immich-app/immich-server:v3\.3\.[0-9]+$'
  - id: ml-url-is-in-cluster-service
    why: >-
      §4.5 reads the server's ML request log for this URL; a repointed ML URL
      would make that gate read an empty set.
    run: kubectl get deploy -n media immich-server -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="IMMICH_MACHINE_LEARNING_URL")].value}'
    expect_exact: http://immich-machine-learning:3003
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/immich.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-10-22"
---

# immich-machine-learning v3.3.3-openvino -> v3.3.5-openvino

## 1. Summary & why held

### 1.1 What changes
One line in `kubernetes/apps/media/immich/app/machine-learning-helmrelease.yaml`:
`tag: v3.3.3-openvino` -> `tag: v3.3.5-openvino` (plus the stale fallback comment
`v3.2.0` -> `v3.3.5`). Flux re-renders `deployment/immich-machine-learning`
(`strategy: Recreate`), the pod restarts once on its node with the same
`/dev/dri` hostPath, `gpu.intel.com/i915: 1` and the same Longhorn `immich-ml-cache`.

### 1.2 Upstream evidence (read 2026-10-22, the G3 gap)
- **v3.3.4** (2026-10-20): "fix: missing translation" and "perf(server): more
  efficient person queries". Both server-side. The release also adds the server
  DB migration `server/src/schema/migrations/1792213725597-AddAssetFaceAssetState.ts`
  (`gh api repos/immich-app/immich/compare/v3.3.3...v3.3.4`) -- **server only**;
  the ML container has no database.
- **v3.3.5** (2026-10-21), section "Security": "chore(deps): update python docker
  digests" (#32635) and "chore(deps): update dependency certifi to v2026.10.19"
  (#32636). Upstream's own caution box recommends updating promptly because of a
  public CA compromise disclosed that day.
- **Full ML diff v3.3.3...v3.3.5** (`compare` API, files under `machine-learning/`):
  exactly three files -- `Dockerfile` (every `python:3.1x-slim-trixie@sha256:` base
  digest moves; `ONNXRUNTIME_VERSION` stays `v1.30.0`), `pyproject.toml` (version
  string 3.3.3 -> 3.3.5) and `uv.lock` (certifi 2025.11.12 -> 2026.10.19 + version
  string). **No Python source, model, API or execution-provider change.**

So the hold was a G3 "release notes unverified" signal, not a breaking-change
signal; after reading the notes the change is a same-behaviour base/dependency
refresh. `risk: low`, `capability_change: false`.

### 1.3 Security driver
Security-driven: `security_ref: F-611ca4c7`. Detail stays on the finding record.
Note for the executor: a pre-plan scan (2026-10-22) shows this bump is the only
available remediation and reduces the fixable set, but does NOT by itself bring it
to zero -- the residual is recorded on the finding record, not here. Expect the
sweep to close F-611ca4c7 (it names the v3.3.3 tag) and re-rate whatever remains
on v3.3.5 under the already-newest rule (AR-029); that re-rating is the sweep's
job, not this window's.

### 1.4 Known pre-existing defect -- do NOT score it against this change
On v3.3.3 today the OpenVINO EP fails to load the OCR **recognition** model
(`/cache/ocr/LATIN__PP-OCRv5_mobile/recognition/model.onnx` -> `RuntimeError:
Preparing ... failed`, 121 occurrences in the current pod's ~6-day log), and the
server logs 13 `Machine learning request ... {"ocr":...} failed with status 500`
in the last 24h. CLIP and face detection/recognition work. 3.3.5 changes neither
onnxruntime nor the model, so this is expected to persist; §4 gates exclude the
OCR class explicitly and compare everything else against zero. It is reported to
the coordinator as a separate finding candidate, not fixed here.

## 2. Pre-checks

Run from `/Users/mu/code/cberg-home-nextgen` on the Mac mini (zsh).

2.1 Premises (frontmatter) all PASS:
```bash
.venv/bin/python3 runbooks/plan-premises.py immich-machine-learning-3.3.5
```

2.2 Flux and workload healthy:
```bash
flux get helmreleases -n media | grep -E 'NAME|immich'        # all four immich-* Ready=True
kubectl get pods -n media -l app.kubernetes.io/name=immich-machine-learning -o wide
# PASS: 1/1 Running. FAIL: anything else -> stop, this is not a clean pre-state.
```

2.3 Target tag exists and record the expected digest:
```bash
TOK=$(curl -s "https://ghcr.io/token?scope=repository:immich-app/immich-machine-learning:pull" | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
curl -sI -H "Authorization: Bearer $TOK" \
  -H 'Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json' \
  https://ghcr.io/v2/immich-app/immich-machine-learning/manifests/v3.3.5-openvino | grep -iE '^(HTTP|docker-content-digest)'
# PASS: HTTP/2 200 and docker-content-digest: sha256:1dbac7f811b51b80c55ee0cf678e0089d3532c798f14a65747d5d7b473a4f9d6
# FAIL: 404, or a different digest (upstream re-pushed the tag) -> stop and re-read §1.2.
```

2.4 Baselines (kept in /tmp only, never committed):
```bash
mkdir -p /tmp/iml-335
# a) Non-OCR ML errors on the current pod (expect 0):
kubectl -n media logs deploy/immich-machine-learning 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' > /tmp/iml-335/ml-before.log
grep -A3 -E 'RuntimeError: *Preparing' /tmp/iml-335/ml-before.log | grep -oE '/cache/[A-Za-z_-]+/[A-Za-z0-9_.-]+/[a-z]+' | sort | uniq -c
# Expected today: only "/cache/ocr/LATIN__PP-OCRv5_mobile/recognition". Any other path = a new pre-existing defect; note it.
# b) Server-side non-OCR ML request failures, last 24h (expect 0):
kubectl -n media logs deploy/immich-server --since=24h 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' \
  | grep -E "Machine learning request '" | grep -vc "request '{\"ocr\""
# c) Fixable-CRITICAL baseline on the CURRENT image (number stays in the terminal / on the finding):
trivy image --severity CRITICAL --exit-code 0 --quiet --format json --timeout 14m \
  ghcr.io/immich-app/immich-machine-learning:v3.3.3-openvino > /tmp/iml-335/trivy-before.json
python3 -c "import json;r=json.load(open('/tmp/iml-335/trivy-before.json'));print(sum(1 for res in r.get('Results',[]) for x in (res.get('Vulnerabilities') or []) if x.get('FixedVersion')))" > /tmp/iml-335/fixable-before.txt
```

2.5 Prometheus reachable and the ML readiness series present (CONTROL instrument exists):
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 2
curl -s 'http://127.0.0.1:19090/api/v1/query' --data-urlencode 'query=sum(kube_pod_status_ready{namespace="media",pod=~"immich-machine-learning-.*",condition="true"})' \
  | python3 -c 'import sys,json;r=json.load(sys.stdin)["data"]["result"];print(r[0]["value"][1] if r else "EMPTY")'
kill $PF 2>/dev/null
# PASS: 1. FAIL: EMPTY (the instrument is blind -> §4.4 cannot gate; stop) or 0.
```

## 3. Steps

3.1 Edit (dry-tested on a scratch copy with BSD sed 2026-10-22; resulting diff below):
```bash
sed -i '' \
  -e 's|tag: v3\.3\.3-openvino$|tag: v3.3.5-openvino|' \
  -e 's|swap to the plain `v3\.2\.0` (CPU) tag|swap to the plain `v3.3.5` (CPU) tag|' \
  kubernetes/apps/media/immich/app/machine-learning-helmrelease.yaml
git diff kubernetes/apps/media/immich/app/machine-learning-helmrelease.yaml
```
Expected diff (exactly two lines changed):
```
<             # Fallback on OpenVINO regressions: swap to the plain `v3.2.0` (CPU) tag.
>             # Fallback on OpenVINO regressions: swap to the plain `v3.3.5` (CPU) tag.
<               tag: v3.3.3-openvino
>               tag: v3.3.5-openvino
```

3.2 Commit **this file only**, in its own commit (never bundled with the immich-server
tag -- see §6), then verify authorship of the commit before pushing:
```bash
cat > /tmp/iml-335/msg.txt <<'EOF'
fix(immich-ml): v3.3.3-openvino -> v3.3.5-openvino (plan immich-machine-learning-3.3.5)

Base-image digests + certifi refresh; no ML code change. security_ref F-611ca4c7.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
git commit --only kubernetes/apps/media/immich/app/machine-learning-helmrelease.yaml -F /tmp/iml-335/msg.txt
git log -1 --format=%s          # must be the subject above; amend before push if not
git show --stat HEAD            # exactly 1 file
git push
```

3.3 Let the Flux webhook reconcile (no manual `flux reconcile` needed). Watch:
```bash
kubectl -n media rollout status deploy/immich-machine-learning --timeout=10m
```
(Rollout status alone is not the gate -- see §4.1.)

## 4. Verification

Wait for the new pod to be Ready, then run all gates. Any FAIL -> §5.

4.1 CONTENTS ASSERTION: the running container is the v3.3.5-openvino index digest --
measured by the pod's `imageID`, compared to the digest recorded in §2.3.
```bash
kubectl -n media get pod -l app.kubernetes.io/name=immich-machine-learning \
  -o jsonpath='{range .items[*]}{.metadata.name} {.status.phase} {.status.containerStatuses[0].imageID}{"\n"}{end}'
# PASS: exactly one pod, Running, imageID ends @sha256:1dbac7f811b51b80c55ee0cf678e0089d3532c798f14a65747d5d7b473a4f9d6
# FAIL: the old digest sha256:43b6b964... (rollout green-lit the old generation), two pods, or Pending
# (i915 or Multi-Attach). The live v3.3.3 pod reports the index digest the same way (measured 2026-10-22).
```

4.2 CONTENTS ASSERTION: inference actually returns real embeddings and face output --
measured by a direct `/predict` call, compared to the v3.3.3 baseline measured
2026-10-22 (textual 512 dims all non-zero; visual 512 dims; facial-recognition key present).
```bash
python3 - <<'EOF'
import zlib,struct
w=h=256
raw=b''.join(b'\x00'+b''.join(bytes([(x*7+y*3)%256,(x*y)%256,(y*5)%256]) for x in range(w)) for y in range(h))
def c(t,d): return struct.pack('>I',len(d))+t+d+struct.pack('>I',zlib.crc32(t+d)&0xffffffff)
open('/tmp/iml-335/probe.png','wb').write(b'\x89PNG\r\n\x1a\n'+c(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+c(b'IDAT',zlib.compress(raw))+c(b'IEND',b''))
EOF
kubectl -n media port-forward svc/immich-machine-learning 13003:3003 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s -m 120 -X POST http://127.0.0.1:13003/predict \
  -F 'entries={"clip":{"textual":{"modelName":"ViT-B-32__openai"}}}' -F 'text=a photo of a dog' \
  | python3 -c "import sys,json;r=json.load(sys.stdin);e=r['clip'];e=json.loads(e) if isinstance(e,str) else e;n=sum(1 for x in e if x!=0);print('TEXT',len(e),n);sys.exit(0 if len(e)==512 and n>500 else 1)" && echo TEXT_PASS || echo TEXT_FAIL
curl -s -m 180 -X POST http://127.0.0.1:13003/predict \
  -F 'entries={"clip":{"visual":{"modelName":"ViT-B-32__openai"}},"facial-recognition":{"detection":{"modelName":"buffalo_l","options":{"minScore":0.7}},"recognition":{"modelName":"buffalo_l"}}}' \
  -F 'image=@/tmp/iml-335/probe.png' \
  | python3 -c "import sys,json;r=json.load(sys.stdin);e=r['clip'];e=json.loads(e) if isinstance(e,str) else e;ok=len(e)==512 and isinstance(r.get('facial-recognition'),list) and r.get('imageWidth')==256;print('VISUAL',len(e),'faces',len(r.get('facial-recognition',[])));sys.exit(0 if ok else 1)" && echo VISUAL_PASS || echo VISUAL_FAIL
kill $PF 2>/dev/null
# PASS: TEXT_PASS and VISUAL_PASS. FAIL: either *_FAIL -- an HTTP 500 / connection refused / a non-JSON body
# makes the python raise (non-zero exit), a zero vector fails the n>500 floor. The probe image has no faces,
# so faces=0 is expected; the gate is that the face pipeline ran (key present, image dims echoed).
```

4.3 CONTENTS ASSERTION: inference still runs on the iGPU, not a silent CPU fallback --
measured from the new pod's log after §4.2 loaded the models.
```bash
kubectl -n media logs deploy/immich-machine-learning 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' > /tmp/iml-335/ml-after.log
grep -c "\['OpenVINOExecutionProvider'" /tmp/iml-335/ml-after.log      # PASS: >= 1
grep -A3 -E 'RuntimeError: *Preparing' /tmp/iml-335/ml-after.log | grep -oE '/cache/[A-Za-z_-]+/[A-Za-z0-9_.-]+/[a-z]+' \
  | grep -vc 'ocr/LATIN__PP-OCRv5_mobile/recognition'                  # PASS: 0
kubectl exec -n media deploy/immich-machine-learning -- ls /dev/dri | grep -c renderD   # PASS: >= 1
# FAIL (1st): the provider list printed on model load is ['CPUExecutionProvider'] only -> 0 matches
# (OpenVINO/iGPU init regressed; v3.3.3 printed ['OpenVINOExecutionProvider', 'CPUExecutionProvider'] on every load).
# FAIL (2nd): any model OTHER than the known-broken OCR recognition model now fails to prepare (§1.4).
```

4.4 Readiness, alerts and restarts:

CONTROL: metric kube_pod_status_ready -- `sum(kube_pod_status_ready{namespace="media",pod=~"immich-machine-learning-.*",condition="true"})` must read 1 (EMPTY or 0 = FAIL; §2.5 proved the series exists).
CONTROL: alertname ImmichMLNotReady -- must NOT be firing 10 min after the new pod is Ready.
CONTROL: alertname ImmichPodCrashLooping -- must NOT be firing.
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 2
curl -s 'http://127.0.0.1:19090/api/v1/query' --data-urlencode 'query=sum(kube_pod_status_ready{namespace="media",pod=~"immich-machine-learning-.*",condition="true"})' \
  | python3 -c 'import sys,json;r=json.load(sys.stdin)["data"]["result"];print(r[0]["value"][1] if r else "EMPTY")'
curl -s http://127.0.0.1:19090/api/v1/alerts | python3 -c "
import sys,json
a=[x['labels']['alertname'] for x in json.load(sys.stdin)['data']['alerts'] if x['state']=='firing' and x['labels'].get('alertname') in ('ImmichMLNotReady','ImmichPodCrashLooping')]
print('FIRING',a) if a else print('NONE_FIRING')"
kill $PF 2>/dev/null
kubectl -n media get pod -l app.kubernetes.io/name=immich-machine-learning -o 'jsonpath={.items[0].status.containerStatuses[0].restartCount}'   # PASS: 0
```

4.5 CONTENTS ASSERTION: the server's real ML traffic succeeds -- measured as server-side
`Machine learning request ... failed` lines whose request is NOT OCR, since the new
pod started, compared to the §2.4b baseline (0).
```bash
SINCE=$(kubectl -n media get pod -l app.kubernetes.io/name=immich-machine-learning -o jsonpath='{.items[0].status.startTime}')
echo "ML pod started $SINCE"
kubectl -n media logs deploy/immich-server --since-time="$SINCE" 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' \
  | grep -E "Machine learning request '" | grep -vc "request '{\"ocr\""
kubectl -n media logs deploy/immich-server --since-time="$SINCE" 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' \
  | grep -cE 'Machine learning server became healthy'
# Pair with the positive checks 4.1-4.4 (pod Ready, /ping ok): a zero count alone is an absence gate.
# PASS: first count 0. (The "became healthy" count >= 1 shows the server re-noticed the backend after the
# Recreate gap; 0 there is acceptable only if the gap was shorter than its ping interval.)
# FAIL: any non-OCR failure line (smart-search / face / CLIP job hit a 500 or refused connection).
```

4.6 Security effect (numbers stay in the terminal and on F-611ca4c7, never in git):
```bash
trivy image --severity CRITICAL --exit-code 0 --quiet --format json --timeout 14m \
  ghcr.io/immich-app/immich-machine-learning:v3.3.5-openvino > /tmp/iml-335/trivy-after.json
python3 -c "
import json
r=json.load(open('/tmp/iml-335/trivy-after.json'))
after=sum(1 for res in r.get('Results',[]) for x in (res.get('Vulnerabilities') or []) if x.get('FixedVersion'))
before=int(open('/tmp/iml-335/fixable-before.txt').read())
print('PASS' if after<before else 'FAIL', '(before/after kept local)')"
# PASS: strictly fewer fixable CRITICAL than v3.3.3 (pre-plan scan 2026-10-22 showed a reduction).
# FAIL: equal or more -> the bump did not deliver its security purpose; keep it (still newest, no
# regression) but record on the finding and tell the operator. Not a rollback trigger on its own.
printf 'immich-machine-learning v3.3.5-openvino applied (plan immich-machine-learning-3.3.5).\nFixable CRITICAL before: %s, after: %s (trivy, --severity CRITICAL).\n' \
  "$(cat /tmp/iml-335/fixable-before.txt)" \
  "$(python3 -c "import json;r=json.load(open('/tmp/iml-335/trivy-after.json'));print(sum(1 for res in r.get('Results',[]) for x in (res.get('Vulnerabilities') or []) if x.get('FixedVersion')))")" \
  > /tmp/iml-335/trivy-summary.md
source runbooks/lib/sweep-pg-dsn.sh && sweep_pg_dsn_up
.venv/bin/python3 runbooks/policy-cli.py finding detail F-611ca4c7 --plan immich-machine-learning-3.3.5 --detail-file /tmp/iml-335/trivy-summary.md   # write the before/after there, not in git
```

## 5. Rollback

Triggers: §4.1, §4.2, §4.3, §4.4 or §4.5 FAIL. (§4.6 alone is not a trigger.)
Nothing is forward-only: ML has no database and the `/cache` models are reused unchanged.

5.1 Revert the ML commit only (never a range that includes an immich-server tag move -- that
would downgrade the server past the 3.3.4 DB migration, the failure of `b9a14f69`/`a844cf8d`):
```bash
git log --oneline -3 -- kubernetes/apps/media/immich/app/machine-learning-helmrelease.yaml   # find the §3.2 sha
git revert --no-edit <sha-from-3.2>
git show --stat HEAD       # exactly machine-learning-helmrelease.yaml
git log -1 --format=%s     # must be the Revert of YOUR commit
git push
```
If `git revert` refuses because the shared index is dirty, do the inverse edit instead and
commit with `--only`:
```bash
sed -i '' -e 's|tag: v3\.3\.5-openvino$|tag: v3.3.3-openvino|' kubernetes/apps/media/immich/app/machine-learning-helmrelease.yaml
git commit --only kubernetes/apps/media/immich/app/machine-learning-helmrelease.yaml -m "revert(immich-ml): back to v3.3.3-openvino (plan immich-machine-learning-3.3.5 rollback)"
git log -1 --format=%s && git push
```

5.2 Alternative if only the OpenVINO path broke (§4.3 first gate FAIL, §4.2 PASS on CPU):
per `docs/sops/immich.md` §11 the documented fallback is the plain CPU tag at the SAME
version (`v3.3.5`). Prefer 5.1 (known-good iGPU state) unless the operator chooses CPU.

5.3 Confirm the cluster is back:
```bash
kubectl -n media get pod -l app.kubernetes.io/name=immich-machine-learning \
  -o jsonpath='{range .items[*]}{.status.containerStatuses[0].imageID}{"\n"}{end}'
# PASS: ends @sha256:43b6b964c6cc458b624ec9b7ed2af0231e19e3bcfaaa68fba8a2668353c48251 (live v3.3.3-openvino today)
```
Then re-run §4.2 and §4.4 -- both must PASS on the rolled-back pod.

## 6. Interference notes

- **Coupling with immich-server-3.3.5 (sibling plan, being written in parallel).**
  Checked, and there is NO hard lockstep:
  - the server talks to ML only via `GET /ping` and `POST /predict`, with no version
    handshake (`server/src/repositories/machine-learning.repository.ts` @ v3.3.5);
  - the ML code is byte-identical 3.3.3 -> 3.3.5 (§1.2);
  - the 3.3.4 DB migration is server-only.

  Either order is safe, and so is a window or two of 3.3.3/3.3.5 skew. The repo
  convention "server + ML pinned to the SAME Immich version" (comment in
  `helmrelease.yaml` line 73, `docs/sops/immich.md` T1) is a tidiness rule, so
  **prefer the same window**. ML first, then server (this plan's order), because it is the cheaper and freely
  reversible leg. That is why `depends_on` is empty: tying ML to a plan whose
  rollback class is restore/forward-only would block a low-risk security bump
  behind a migration gate for no technical reason. It is also why there is no
  `conflicts_with` against it: same-window is the desired outcome.
- **Separate commits are mandatory.** On 2026-10-12 an auto-revert of the grouped
  monorepo bump (`b9a14f69`) downgraded the server past applied migrations and had
  to be rolled forward (`a844cf8d`). Keep the ML tag in its own commit, revert only
  that commit, and never let a batch revert of this plan touch `helmrelease.yaml`.
- **iGPU:** the new pod re-requests `gpu.intel.com/i915`. Recreate frees the old slot
  first, and there is headroom (5 per node; 4 used on nuc14-01 today). Do not run this
  in the same slot as a Talos node roll (`talos-linux-1.14.4`, which is `exclusive: true`
  and so already self-excluding) or an intel-device-plugin change.
- **Prometheus:** §2.5/§4.4 read it, so this plan conflicts with both
  kube-prometheus-stack drafts. `kube-prometheus-stack-92.10.1` is also `exclusive`.
- **User impact:** about 1-3 minutes with no ML backend during Recreate. The library,
  browsing and playback keep working; smart search, face and CLIP jobs queue and retry.
  `ImmichMLNotReady` has `for: 5m`, so a normal Recreate does not fire it.
- **Do not score the OCR recognition failure (§1.4) as a regression.** It predates
  this change and 3.3.5 does not touch it.
