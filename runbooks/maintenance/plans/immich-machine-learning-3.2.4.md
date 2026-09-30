---
plan_id: immich-machine-learning-3.2.4
component: immich-machine-learning
pr: null                              # No Renovate PR. Surfaced by coverage.py as lane=PLAN
                                      # (G3 "release notes unavailable"; earned autonomy 0/0 in 90d).
kind: image
current: "v3.2.2-openvino"            # live 2026-09-30: deploy image ghcr.io/immich-app/immich-machine-learning:v3.2.2-openvino,
                                      # pod imageID @sha256:4013ec28ccf6344d7ae24554743a116d7f61124b98858f5646a401d5c5df12e2
                                      # (== ghcr index digest of v3.2.2-openvino), node k8s-nuc14-03.
target: "v3.2.4-openvino"             # ghcr index digest sha256:ee28c9419670b7f4c17765fb089527eff977deb8e8fb83e714aa1fa57aa89736
                                      # (HEAD manifests/v3.2.4-openvino, 2026-09-30); amd64 child
                                      # sha256:9249078942f49455c0b8ed9d2d986a6e754b9401d966ba93e32f8a2c4946dd0c,
                                      # label org.opencontainers.image.version=v3.2.4, revision db355f79d.
update_type: patch
risk: low                             # The hold is a FALSE POSITIVE of G3 (see §1): the upstream
                                      # machine-learning/ tree changed only its version string between
                                      # v3.2.2 and v3.2.4; the Dockerfile blob is byte-identical.
est_duration_min: 25                  # pre-checks 5 + edit/commit/push/Flux ~5 + pull ~641 MB new layers
                                      # + Recreate (~20 s to Ready measured 2026-09-27) + §4 ~8.
needs_reboot: false
touches:
  namespaces: [media]
  resources:
    - helmrelease/immich-machine-learning   # the edit (kubernetes/apps/media/immich/app/machine-learning-helmrelease.yaml)
    - deployment/immich-machine-learning    # strategy Recreate (live): one pod replaced
    - service/immich-machine-learning       # unchanged; endpoints move to the new pod (~1 min gap)
    - pvc/immich-ml-cache                   # longhorn RWO 30Gi (model cache, derived data); remounted, not modified
  shared: [igpu-i915]                 # pod requests+limits gpu.intel.com/i915: 1 (5 slots/node; live
                                      # consumers 2026-09-30: nuc14-03 scrypted + immich-ml; nuc14-01
                                      # immich-server, jellyfin, makemkv; nuc14-02 frigate, plex).
                                      # Recreate frees the slot before the new pod claims one.
depends_on: []
conflicts_with:
  - app-template-5.2.1                # its Batch A edits THIS HelmRelease file (chart line) and its §4
                                      # workload compare would read our Recreate as its own roll.
  - redis-fleet-8.10.2                # rolls media/immich-redis AND deployment/immich-server; our §4.4
                                      # gate reads immich-server's log for the ML health transition.
  - jellyfin-12.1                     # igpu-i915 consumer in media; two i915 Recreates in one window
                                      # confound both GPU gates.
  - jellyfin-config-rwo-migration     # igpu-i915 consumer in media (same reason).
  - helm-drift-detection              # adds driftDetection to this HR AND its P2 re-apply rolls the
                                      # intel-gpu-plugin DaemonSet (i915 re-register under our new pod).
  - flux-reconciler-impersonation     # exclusive:true already keeps its slot empty; named for reciprocity
                                      # with the other media/i915 plans.
  - float-tag-pinning                 # blocked; re-claims an i915 slot on its consumer when it runs.
exclusive: false
security_ref: F-5ca2e3d9              # security driver on the CURRENT image; detail on the DB record only.
capability_change: false              # same-behaviour patch: upstream ML source diff v3.2.2..v3.2.4 is the
                                      # version string in pyproject.toml + uv.lock only; no new route,
                                      # permission, API or exposure (ClusterIP only, no HTTPRoute).
rollback_class: git-revert            # nothing forward-only: ML is stateless; /cache holds downloaded
                                      # model files keyed by model name, identical for both versions.
finding_refs: [F-5ca2e3d9, F-6d0f4efc]  # security finding (current image) + the version finding for this bump.
review: null
status: draft
window: null
premises:
  - id: ml-image-is-v3.2.2-openvino
    why: >-
      `current:` and every baseline below were captured against this pin. If the
      Deployment already moved, this plan is stale.
    run: kubectl get deploy -n media immich-machine-learning -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/immich-app/immich-machine-learning:v3.2.2-openvino
  - id: server-already-v3.2.4
    why: >-
      This plan closes the one-patch skew created by the 2026-09-30 Step 0
      direct-bump of immich-server (3e222f1d). If the server was reverted, the
      bump would CREATE a skew instead of closing it; stop and re-assess.
    run: kubectl get deploy -n media immich-server -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/immich-app/immich-server:v3.2.4
  - id: ml-hr-ready
    why: "A HelmRelease already failing would mask whether the bump itself reconciled."
    run: kubectl get helmrelease -n media immich-machine-learning -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: ml-strategy-recreate
    why: >-
      Single replica on an RWO Longhorn PVC (immich-ml-cache). A RollingUpdate
      could Multi-Attach-deadlock if the new pod lands on another node
      (docs/sops/longhorn-rwo-multi-attach.md).
    run: kubectl get deploy -n media immich-machine-learning -o jsonpath='{.spec.strategy.type}'
    expect_exact: Recreate
  - id: ml-not-alerting
    why: "ImmichMLNotReady must be quiet before the change, or §4.5 cannot attribute a firing to it."
    run: kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=ALERTS%7Balertname%3D%22ImmichMLNotReady%22%7D'
    expect_contains: '"result":[]'
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/immich.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-09-30"
---

# immich-machine-learning v3.2.2-openvino -> v3.2.4-openvino

## 1. Summary & why held

One-line image-tag bump of the Immich machine-learning container (OpenVINO /
Intel-iGPU flavour) in `kubernetes/apps/media/immich/app/machine-learning-helmrelease.yaml`,
bringing it level with `immich-server`, which Step 0 of nightly 2026-09-30
direct-bumped to `v3.2.4` (commit `3e222f1d`, green).

**Security driver:** `security_ref: F-5ca2e3d9` (detail on the DB record only).
No newer tag exists beyond v3.2.4 at time of writing; this is the "bump to a
newer upstream tag" remediation.

**Why held (G3, "release notes unavailable") — a false positive.** The release
notes exist: GitHub release `immich-app/immich` `v3.2.4` (published
2026-09-28T16:52Z). `check-all-versions.py` maps this image to the
`immich-app/immich` repo but `IMAGE_TAG_FLAVOUR_SUFFIXES` has no entry
stripping `-openvino`, so G3 asked for a release literally named
`v3.2.4-openvino`, which does not exist. (The in-code comment next to the map
entry already calls this "a separate, un-fixed gap"; see the report for the
repo correction.)

**What upstream actually changed (primary sources, read 2026-09-30):**

- Release notes v3.2.4: *"Just another small patch that primarily fixes the
  memory leak people have observed through a dependency update."* One listed
  bug fix, mobile-only (#31644, sync status page). v3.2.3 was an unpublished
  "sacrificed" release.
- `gh api repos/immich-app/immich/compare/v3.2.2...v3.2.4`: 4 commits. Under
  `machine-learning/` the ONLY change is `version = "3.2.2"` -> `"3.2.4"` in
  `pyproject.toml` and `uv.lock`. The "dependency update" is commit
  `6786b82b6` (base-image `v202609281550`) and touches `server/Dockerfile`
  only — i.e. the memory-leak fix is in the server image, already landed.
- `machine-learning/Dockerfile` blob sha is identical at both tags
  (`c8191e30…`): same pinned `python:3.13-slim-trixie` base digest, same
  pinned Intel IGC / compute-runtime `.deb` versions, same `uv sync --frozen`.
- Registry: of 12 amd64 layers, 5 are shared (the Python base); the rest are
  rebuilt (the `apt-get update` + lockfile-install layers pick up refreshed
  distro packages at build time — that is where the security driver is
  addressed). Entrypoint/Cmd (`tini -- python -m immich_ml`) and
  `DEVICE=openvino` are unchanged.

**Server/ML version skew (v3.2.4 server, v3.2.2 ML) — does it matter?**
Functionally no. The server's ML client (`server/src/repositories/machine-learning.repository.ts`
at v3.2.4) only calls `GET /ping` and `POST /predict`; there is no version
handshake, and the ML request/response code is unchanged between the tags.
Live proof: the v3.2.4 server logged `Machine learning server became healthy
(http://immich-machine-learning:3003)` for both its Api and Microservices
processes at 03:33 against the v3.2.2 ML pod. The skew does violate the
house convention in `docs/sops/immich.md` ("keep `<ver>` IDENTICAL to the
`immich-server` pin"), which is a reason to close it, not an outage.

Verdict: risk low; the hold was a gate false-positive. The only real risk is
the generic one for this image — an OpenVINO/iGPU init regression in a rebuilt
image — which §4.3 tests directly and §5 reverses in one commit.

## 2. Pre-checks

Run from the repo root on the Mac mini (zsh).

2.1 Premises (fail-closed):
```bash
.venv/bin/python3 runbooks/plan-premises.py immich-machine-learning-3.2.4
```
All five must PASS. Stop on any failure.

2.2 Flux healthy for the app:
```bash
flux get helmreleases -n media | grep -E 'NAME|immich'
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
```
PASS: all four `immich-*` HRs `True`; the second command prints only its header.

2.3 Baseline the ML probe (proves the §4.3 instrument works BEFORE the change):
```bash
kubectl port-forward -n media svc/immich-machine-learning 13003:3003 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s -m 10 localhost:13003/ping; echo
curl -s -m 120 -X POST localhost:13003/predict \
  -F 'entries={"clip":{"textual":{"modelName":"ViT-B-32__openai"}}}' -F 'text=a photo of a dog' \
  | python3 -c 'import sys,json;d=json.load(sys.stdin);c=d["clip"];v=json.loads(c) if isinstance(c,str) else c;print("dim",len(v),"nonzero",sum(1 for x in v if x!=0))'
curl -s -m 60 -X POST localhost:13003/predict \
  -F 'entries={"clip":{"textual":{"modelName":"NoSuchModel__x"}}}' -F 'text=x'; echo
kill $PF 2>/dev/null
```
Expected (measured live 2026-09-30 04:16 against v3.2.2-openvino): `pong`,
`dim 512 nonzero 512`, and `Internal Server Error` for the negative control.
If the positive probe already fails here, the ML service is broken today — stop.

2.4 No other i915 consumer is mid-Recreate:
```bash
kubectl get pods -A -o wide | grep -E 'scrypted|frigate|jellyfin|plex|makemkv|immich' | grep -vE 'Running|Completed'
```
PASS: no output.

## 3. Steps

3.1 Edit the tag (dry-tested with BSD sed on a scratch copy 2026-09-30; exactly
one line changes):
```bash
F=kubernetes/apps/media/immich/app/machine-learning-helmrelease.yaml
sed -i '' 's|^\([[:space:]]*tag: \)v3\.2\.2-openvino$|\1v3.2.4-openvino|' "$F"
git diff -- "$F"
```
Expected diff (verified on the scratch copy):
```
-              tag: v3.2.2-openvino
+              tag: v3.2.4-openvino
```
If `git diff` shows anything else (or nothing), stop.

3.2 Commit only that file and push:
```bash
cat > /tmp/immich-ml-msg.txt <<'EOF'
chore(immich): bump immich-machine-learning v3.2.2-openvino -> v3.2.4-openvino (plan immich-machine-learning-3.2.4)

Closes the one-patch skew with immich-server v3.2.4 (3e222f1d).
security_ref F-5ca2e3d9.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
git commit --only kubernetes/apps/media/immich/app/machine-learning-helmrelease.yaml -F /tmp/immich-ml-msg.txt
git log -1 --format=%s          # must be the subject above
git show --stat HEAD            # exactly one file
git push
```
Record the commit sha as `$BUMP_SHA` for §5.

3.3 Let the Flux webhook reconcile (no manual reconcile). Wait for the rollout:
```bash
kubectl rollout status deploy/immich-machine-learning -n media --timeout=15m
```
`rollout status` can green-light the old generation — §4.1 asserts the live
pod's digest, which is the real gate.

## 4. Verification

4.1 Live pod runs the target image (not the old generation):
```bash
kubectl get deploy -n media immich-machine-learning -o jsonpath='{.spec.template.spec.containers[0].image}'; echo
kubectl get pod -n media -l app.kubernetes.io/instance=immich-machine-learning \
  -o jsonpath='{range .items[*]}{.metadata.name} {.status.containerStatuses[0].imageID} ready={.status.containerStatuses[0].ready} restarts={.status.containerStatuses[0].restartCount} node={.spec.nodeName}{"\n"}{end}'
```
PASS: image `...:v3.2.4-openvino`; exactly ONE pod; imageID ends
`@sha256:ee28c9419670b7f4c17765fb089527eff977deb8e8fb83e714aa1fa57aa89736`;
`ready=true restarts=0`. FAILS if Flux never applied (image still v3.2.2),
if the old pod is still the only one (imageID `4013ec28…`), or on a crash loop.

4.2 iGPU still presented to the container:
```bash
kubectl exec -n media deploy/immich-machine-learning -- ls /dev/dri
```
PASS: output contains `renderD128`. FAILS (no such file / empty) if the
hostPath or i915 allocation broke.

4.3 CONTENTS ASSERTION: the ML service returns real embeddings AND selects
the OpenVINO provider — measured by re-running the exact §2.3 probe block
against the NEW pod, then:
```bash
kubectl logs -n media deploy/immich-machine-learning | sed 's/\x1b\[[0-9;]*m//g' \
  | grep -ic 'OpenVINOExecutionProvider'
```
PASS: `pong`; `dim 512 nonzero 512` (compared to the §2.3 baseline of 512/512);
negative control still `Internal Server Error`; the provider count is `>= 1`.
What failure prints: an OpenVINO/iGPU init regression either crashes the model
load (the positive probe prints `Internal Server Error` / a Python traceback,
and `json.load` raises) or silently falls back to CPU, in which case the
"Setting execution providers to" line lists only `CPUExecutionProvider` and
the grep prints `0`. The `sed` strips ANSI colour (the ML log is rich-coloured,
and the provider list wraps over two lines — the token itself is never split;
measured 2026-09-30). The negative control proves the endpoint discriminates
(an unknown model raises `ValueError: Unknown model combination`, so a
blanket-200 proxy would fail it). The pod is fresh, so the log contains only
this probe's model load.

4.4 CONTENTS ASSERTION (consumer side): immich-server re-established its ML
backend — measured by the LAST ML-health transition line of each server
process:
```bash
kubectl logs -n media deploy/immich-server -c main | sed 's/\x1b\[[0-9;]*m//g' \
  | grep 'Machine learning server became' | awk '{p=($0 ~ /Microservices:/)?"micro":"api"; last[p]=$0} END{for(k in last) print k": "last[k]}'
```
PASS: two lines (`api:` and `micro:`), each ending `became healthy (http://immich-machine-learning:3003).`
Source: `setHealthy()` in `machine-learning.repository.ts` logs only on a
healthy/unhealthy TRANSITION, from a periodic `GET /ping`. If the new ML pod
never comes up, the last line reads `became unhealthy`; if the Recreate gap fell
between two pings, no new line appears and the 03:33 `healthy` line remains
last — correct either way. Wait ≥ 2 min after 4.1 passes before reading.

4.5 Alerts quiet:
```bash
kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=ALERTS%7Balertname%3D~%22Immich.%2A%22%2Calertstate%3D%22firing%22%7D'; echo
kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=kube_deployment_status_replicas_available%7Bnamespace%3D%22media%22%2Cdeployment%3D%22immich-machine-learning%22%7D' \
  | python3 -c 'import sys,json;r=json.load(sys.stdin)["data"]["result"];print("series",len(r),"value",r[0]["value"][1] if r else "EMPTY")'
```
CONTROL: alertname ImmichMLNotReady — must NOT be firing (`"result":[]`) ≥ 6 min after 4.1 (rule `for: 5m`).
CONTROL: alertname ImmichPodCrashLooping — must NOT be firing.
CONTROL: metric kube_deployment_status_replicas_available — `series 1 value 1` for the ML deployment; `EMPTY` is a FAIL (the instrument went blind, not a pass).

4.6 Thermal sanity (the ML pod may land on any node; the CPU cap of 3 is unchanged):
```bash
kubectl get deploy -n media immich-machine-learning -o jsonpath='{.spec.template.spec.containers[0].resources.limits.cpu}'; echo
```
PASS: `3`.

## 5. Rollback

Trigger: any §4 gate fails.

5.1 Preferred — revert to the previous build:
```bash
git revert --no-edit $BUMP_SHA
git log -1 --format=%s          # must be the Revert of the bump subject
git push
kubectl rollout status deploy/immich-machine-learning -n media --timeout=15m
```
5.2 Confirm the cluster is back: §4.1 with the old values — image
`...:v3.2.2-openvino`, one pod, imageID ends
`@sha256:4013ec28ccf6344d7ae24554743a116d7f61124b98858f5646a401d5c5df12e2`,
`ready=true`; then re-run §4.3 (expect 512/512 and provider count >= 1) and
§4.4. v3.2.2 ML with v3.2.4 server is the state that ran green all morning
of 2026-09-30 (skew is harmless, §1).

5.3 Alternative if ONLY the OpenVINO path regressed and the security driver
must still land: the SOP-documented CPU fallback — change the tag to the plain
`v3.2.4` (index digest `sha256:e16c2f166a8174901959fdf85e2e4c7bd1ebc4b37e0b6655de97c41408a260c4`,
verified present on ghcr 2026-09-30). That is a behaviour change (CPU inference,
slower smart search/face jobs, CPU capped at 3) and therefore an operator
decision, not an automatic step.

Nothing forward-only happens: no DB, no schema, the model cache is keyed by
model name and shared by both versions. No backup/restore is required.

## 6. Interference notes

- **i915 (`igpu-i915`)**: the Recreate releases one `gpu.intel.com/i915` slot
  and re-claims one; with 5 slots per node and at most 2 used on any node
  today, scheduling cannot starve. Do not run in the same window as another
  i915 consumer's Recreate or an intel-gpu-plugin roll (hence
  `conflicts_with`: jellyfin-12.1, jellyfin-config-rwo-migration,
  helm-drift-detection, float-tag-pinning).
- **Same file as app-template-5.2.1** (chart `5.1.0 -> 5.2.1` line). Different
  line, so no merge conflict, but its §4 workload-generation compare would
  count our Recreate — keep them in separate windows.
- **redis-fleet-8.10.2** restarts immich-server, whose log §4.4 reads.
- **User impact**: ~1-2 min without smart search / face / OCR inference. The
  server keeps serving the library; jobs that hit the gap fail and are re-run
  by the server's queue. The nightly ML jobs start at 00:00 (model loads seen
  00:00:40-00:00:48 both nights), well before the 03:30 nightly window.
- **Prometheus** is read in §4.5; no kube-prometheus-stack plan is open
  (91.4.1 executed). A future one must be added to `conflicts_with` here.
- **Neighbours on the pod's node**: the CPU limit of 3 (permanent thermal
  bound, operator decision 2026-08-09) is untouched by this plan.
