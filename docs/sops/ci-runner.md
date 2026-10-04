# SOP: CI Runner — The Ninth Banner test suites as sharded Kubernetes Jobs

> Description: How The Ninth Banner's test suites (unit/check, Playwright e2e, responsive, simulation sweeps) run as ephemeral, sharded, locked-down Kubernetes Jobs in the `ci-runner` namespace, triggered with one command from the Mac mini, and how results are collected.
> Version: `2026.10.04`
> Last Updated: `2026-10-04`
> Owner: `homelab operator (cberg-home-nextgen)`

---

## 1) Description

The Mac mini also hosts the shared Ollama runtime and many agent sessions. Parallel Playwright runs drove its load to 110–170. This runner moves the game's test suites onto the three Talos nodes, which have plenty of idle CPU, while a namespace quota keeps production headroom.

**Status: best-effort.** GitHub Actions CI stays the release gate. The runner is capped for node temperature: 4 CPU per shard, and since 2026-10-04 a **live thermal gate** (§2b) decides where and when each shard starts (up to 6 shards, at most 2 per node, only on nodes below 85 °C), and at that size a few CPU-timing e2e assertions can fail. A red shard here is a signal to re-check on GitHub CI, not a release blocker.

- Scope: namespace `ci-runner`, Flux Kustomization `flux-system/the-ninth-banner-tests`, trigger `scripts/ninth-banner-test.sh`, private repo `nachtschatt3n/the-ninth-banner`.
- Prerequisites: run from this repo on the Mac as `mu`, with the `mise` tool chain (kubeconfig) and `gh` authenticated as the repo owner (used only to resolve a ref to a full SHA).
- Out of scope: GitHub Actions CI (it keeps running independently), deploying the app (see `docs/applications.md`).

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Namespace | `ci-runner`, PSA **restricted**, deliberately **without** the `common` component, so it holds no `cluster-secrets` and no `sops-age` |
| Static infra (GitOps) | `kubernetes/apps/ci-runner/the-ninth-banner-tests/app/`: ServiceAccount (no token, no RBAC), ResourceQuota + LimitRange, CiliumNetworkPolicy, scripts ConfigMap, git credential (SOPS) |
| Flux Kustomization | `flux-system/the-ninth-banner-tests` (lives in `flux-system`, `targetNamespace: ci-runner`) |
| Job template | `kubernetes/apps/ci-runner/the-ninth-banner-tests/job-template.yaml.tpl`. Not applied by Flux and not scanned by kubeconform (`.tpl`); rendered per run by the trigger |
| Trigger | `scripts/ninth-banner-test.sh <ref> <unit\|e2e\|nightly\|responsive\|release\|sims> [shards]` |
| Image | `mcr.microsoft.com/playwright:v1.63.0-noble@sha256:eff16c30…` (multi-arch index digest; Node 24, git, Chromium/Firefox/WebKit baked in). **Keep in lockstep with `@playwright/test` in the game's `package-lock.json`**. Bump: §4 step 5 |
| Thermal gate | Every shard pod is created **gated** (`schedulingGates: ci.cberg.home/thermal`) and admitted onto a cool node with a free CI slot by `scripts/ninth-banner-admit.py`, ticked by every running trigger. See §2b |
| Job shape | Indexed Job, `completions = shards`, `parallelism = min(shards, 3)` in GPU mode, `min(shards, 2)` in CPU mode (**thermal cap**), `backoffLimitPerIndex: 0`, `maxFailedIndexes = shards` (no retries, one failing shard never stops the others), topology spread over `kubernetes.io/hostname`, `activeDeadlineSeconds: 5400`, `ttlSecondsAfterFinished: 3600` |
| Per shard | requests 2 CPU / 6Gi / 8Gi ephemeral; limits **4 CPU (thermal cap)** / 10Gi / 16Gi; Playwright `--workers=2` (`WORKERS`, default 2, see Troubleshooting). emptyDir caps: `work` 10Gi, `tmp` 4Gi, **`results` 6Gi** (raised from 2Gi on 2026-10-04: the `release` shard holding the responsive screen tours (iPad/desktop screenshots) + perf specs was evicted twice with `Usage of EmptyDir volume "results" exceeds the limit "2Gi"` although all its tests passed; the other shards write 2-3 MB). Measured `work` is ~0.8Gi, so the unchanged 16Gi container limit still covers a full `results` dir (each node has 340Gi+ free for 3 parallel shards). `run.sh` logs `results size:` plus the 10 largest entries (`du:` lines) right before `CI-RESULT`, so an oversize run shows what filled it |
| Priority | `PriorityClass ci-low` (value -1000, `preemptionPolicy: Never`, cluster-scoped, in the app kustomization): CI pods never preempt production and are evicted first under node pressure |
| Quota | **6 pods**, requests 12 CPU / 36Gi, limits 24 CPU / 60Gi, i915 6 (since 2026-10-04; was 4 pods / 6.5 CPU, i.e. 3 shards). The quota is only the TOTAL cap; per-node placement is the thermal gate's (§2b). 0 Services, 0 PVCs. Further runs queue (their shards are not created until quota frees) rather than squeezing production. `KubeQuotaAlmostFull`/`KubeQuotaFullyUsed` exclude `ci-runner` (the quota is a cap runs fill by design); `KubeQuotaExceeded` stays stock; a run starved by the quota raises `CIRunnerJobStarved` (info) after 60m |
| Egress | DNS (kube-dns, L7 DNS proxy) answering ONLY `github.com`, `registry.npmjs.org` and `**.cluster.local` (search-domain expansions); everything else REFUSED. TCP 443 to those two hosts only. Ingress: deny all. Both ServiceAccounts (`default` included) have `automountServiceAccountToken: false` |
| Credential | `the-ninth-banner-git-credential` (dockerconfigjson). Mounted **only** into the `clone` init container, read by `git-askpass.sh`; never in env, logs, or the test container |
| Results | `~/ci-results/<job>/` on the Mac: `summary.txt`, `shard-N.log`, `shard-N/{junit.xml, playwright-report/, test-results/ (traces), blob-report/, reports/, exit-code, commit}`; combined suites (`release` via `release-all`) put that layout once per part under `shard-N/<part>/` |

Measured runtimes (2026-10-03, commit `46eaae3`, wall clock from the trigger):

| Run | Result | Wall time |
|---|---|---|
| `unit` (1 shard) | PASS, 38 files / 437 tests (+typecheck, lint, data, build, security) | 52 s incl. first image pull; suite 14 s |
| `e2e` 3 shards, `WORKERS=2` | PASS 77/77, 0 flaky, one shard per node | 9 min 10 s (longest shard 8.9 min) |
| `e2e` 3 shards, `WORKERS=4` | FAIL (CPU-starved timing tests) | 14 min 35 s |
| `e2e` 3 shards, 4-CPU cap, `WORKERS=2`, per-push grep (`0fa1537`, larger suite) | 130 passed / 6 failed (CPU timing: 120 s timeouts, title-ready < 3 s, music render speed) | 34 min incl. queueing; nodes still peaked at 100–101°C with an overlapping 6-CPU run from another session |

Suites (since game `77764e6` the runner calls the game's own shard scripts with `E2E_OUT=/results/shard-N`; the game owns selection, duration-balanced sharding, reporters and the GPU check. Contract: the-ninth-banner `docs/testing/test-execution-strategy.md`, "Hand-off to cberg-agent". Browser suites at refs before the split are refused):

| Suite | What runs | Default shards |
|---|---|---|
| `unit` | `npm run check && npx tsx tools/story-check.ts && npm run test:ci -- --no-build` (GitHub "Check & test" minus the Docker build) | 1 (forced) |
| `e2e` | `npm run test:e2e:shard -- i N` (the game's former per-push selection). **GPU only**: refused with `GPU=0` (CPU/SwiftShader fails its timing budgets) | 3 |
| `nightly` | `npm run test:nightly:shard -- i N` (`@nightly`: multi-seed determinism, music render) | 3 |
| `responsive` | `npm run test:responsive:shard -- i N` (iPad/laptop matrix, WebKit + Chromium). **GPU only** | 3 |
| `release` | **THE release suite on hardware WebGL**: `unset CI`, `PW_GPU_EXPECTED=1`, `PW_CHROMIUM_ARGS=<Intel flags>`, `E2E_RUNNER=k8s`, `npm run test:release-all:shard -- i N --retries=1`: the release suite (every spec except `@art`/`@visual`, incl. the `@perf` fps budgets) plus the responsive matrix, planned by the game as ONE duration-weighted pool over every shard (k8s speed factors via `E2E_RUNNER`); results per part in `shard-N/release/` and `shard-N/responsive/`. Refs before `release-all` fall back to `test:release:shard` with the whole responsive matrix on shard 1 (~13 min instead of ~5-6). The game's `gpu-check` fails a shard in seconds if it renders in software. When every shard has reported, the trigger posts the commit status **`E2E (GPU, k8s)`** (success/failure, counts from the shards' junit) on the game repo with the Mac's `gh`; never for a partial run. **GPU only** | 3 |
| `sims` | CI nightly sweeps (`sim --n 30 --check`, `gen-sweep --n 2000`, `autoplay --n 10 --check`, `ending-hunt --n 4`), round-robin over shards | 4 |

---

## 2a) GPU mode (Intel iGPU, default for browser suites since 2026-10-03)

| Item | Value |
|---|---|
| Hardware | Each NUC14: Meteor Lake **Intel Arc Graphics (MTL)**, PCI `8086:7D55`, driver **i915** (kernel 6.18 Talos), plus an NPU (`npu.intel.com/accel`, not used here) |
| How a pod gets it | The existing Intel GPU device plugin (`kubernetes/apps/kube-system/intel-device-plugin/gpu`, `sharedDevNum: 5`) offers `gpu.intel.com/i915: 5` per node: 5 pods may **share** the one iGPU. A GPU shard requests 1. **No hostPath, no PSA change**: containerd hands the pod `/dev/dri/renderD128` **and `card0`** (the plugin passes both) chowned to its `runAsUser:runAsGroup` (1001), so `ci-runner` stays `restricted` |
| Image | No derived image: the pinned Playwright image already contains Mesa 25.2.8 (`iris`). It has no Vulkan ICD, so ANGLE-Vulkan falls back to SwiftShader; use GL/EGL |
| Flags | `--use-gl=angle --use-angle=gl-egl --ignore-gpu-blocklist --enable-gpu-rasterization`, passed as `PW_CHROMIUM_ARGS`, which the game applies in `playwright.config.ts` and in specs with their own launch options (perf.spec). The earlier runner-side browser-binary wrapper was removed once the game took this over (`77764e6`). Firefox and WebKit stay on software rendering |
| Proof per shard | `run.sh` logs `WebGL renderer: ANGLE (Intel, Mesa Intel(R) Arc(tm) Graphics (MTL), OpenGL ES 3.2)`; anything else logs `GPU-FALLBACK` (the run continues on CPU) |
| Sharing | Other GPU tenants per node (2026-10-03): nuc14-01 immich-server, jellyfin, makemkv (3/5); nuc14-02 frigate, plex (2/5); nuc14-03 scrypted, immich-ml (2/5). A CI shard is a short burst of WebGL; transcodes and detectors share the same iGPU time-sliced. If a node has no free slot, the shard waits in Pending until one frees |
| Fallback | `GPU=0 scripts/ninth-banner-test.sh <ref> e2e`: no GPU request, no flags, SwiftShader (slow and hot; see the CPU measurements) |

Measured 2026-10-03, game commit `302a819`, smoke + perf + journeys specs, Chromium, 1 shard, 2 workers, 4 CPU limit:

| | CPU (SwiftShader) | GPU (Intel Arc) |
|---|---|---|
| WebGL renderer | SwiftShader (Vulkan/Subzero) | Mesa Intel Arc Graphics (MTL) |
| Battle fps (perf.spec) | 6.2 (occlusion: 6.9) | 60.3 (occlusion: 60.1), vsync-capped |
| Long journey (character creator → world) | 266 s | 15 s |
| Mission loop journey | 264 s | 17 s |
| "Title ready within 3 s" | FAIL (11.9 s) | pass (1.3 s) |
| Test time for the 13 tests | 548 s, 3 failed | 61 s, all passed |
| Runner CPU-seconds | 2,202 | 178 |
| Node package temp, peak | 76 °C | 66 °C (node's own baseline before: 76-79 °C) |

Full `e2e` (3 shards, parallelism 2, GPU): **135/136 passed in 5 min 5 s** wall time (the 4-CPU CPU run took ~34 min with 6 failures). Peak 89 °C on the node that ran two shards back to back (77 / 66 °C on the others). The one failure was Firefox `music.spec` (AudioContext `suspended`), which fails on the CPU path too, so it is not GPU-related. Power: not measurable from Prometheus (no RAPL/power collector is scraped), so CPU-seconds is the energy proxy.

Security model for GPU mode (review 2026-10-03, no critical findings):
- The quota caps `requests.gpu.intel.com/i915` at 3 and pins `gpu.intel.com/monitoring`, `i915_monitoring` and `npu.intel.com/accel` to 0, so a CI pod can never get the plugin's all-device monitoring resource or the NPU.
- **ACCEPTED RISK (owner, 2026-10-03), residual:** untrusted npm/test code gets ioctl access to the i915 kernel driver (a kernel exploit would mean node root), and `card0` would let the first opener become DRM master on these headless nodes. Mitigations: non-root, all capabilities dropped, own-repo and lockfile-pinned code only, egress locked down, `GPU=0` fallback. **Never use GPU mode for third-party or forked refs.** Keep Talos on current patch releases (i915 CVEs now matter for this namespace).
- Cross-tenant GPU memory leakage: low (per-process GPU address spaces, zeroed buffers). DoS: bounded. Frigate's detector runs on the NPU; transcodes use the video engines; render contention with immich-ml and tone-mapping is time-sliced, with per-context hang resets.
- Register entry, prepared but not yet recorded (owner or an operator session runs it, as for W1):
  ```bash
  runbooks/policy-cli.py risk add AR-<next> --register-only register-only:posture --severity medium \
    --description 'ci-runner GPU mode: shared i915 render+card0 node exposed to CI test code' \
    --justification 'Owner-requested GPU acceleration 2026-10-03; non-root, caps dropped, own-repo pinned code only, egress-locked, quota caps GPU/monitoring/NPU, GPU=0 fallback; no third-party refs.' \
    --expires 2027-01-01
  ```

Limits / caveats:
- Flag set and GPU check are owned by the game since `77764e6` (`PW_CHROMIUM_ARGS`, `PW_GPU_EXPECTED`); keep the flags in `scripts/ninth-banner-test.sh` in sync with the game's strategy doc.
- Parallelism: **GPU mode runs up to 3 shards at once, one per node** (owner decision 2026-10-03). CPU mode (`GPU=0`) stays at 2 (thermal). CPU cap per shard stays 4.
  Verified 2026-10-03 at `302a819`, 3 GPU shards in parallel (one per node, all on the Intel renderer): **3 min 54 s** wall time, 134/136 passed (1 flaky). Peak package temperatures 69 / 83 / 77 °C (nuc14-01/02/03), against 64 / 81 / 69 °C in the 10 min before. The failure is the known Firefox `music.spec` AudioContext issue (it fails on CPU too).
  `release` with `release-all` verified 2026-10-03 at game `4f26442`, 3 GPU shards: **6 min 57 s** wall time (was ~13 min with the whole responsive matrix on shard 1); shards 309 / 357 / 400 s test time; 188 passed, 0 failed, 26 skipped (3 flaky, passed on retry); status `E2E (GPU, k8s)` = success. Peak package temperatures 71 / 92 / 83 °C (nuc14-01/02/03) against 64 / 76 / 65 °C in the 10 min before; nuc14-02 is the warm node and touched 92 °C, just under the 93 °C target.


## 2b) Thermal gate (since 2026-10-04)

The quota allows 6 shards, but **where and when** a shard starts is decided live from each node's package temperature. The NUC14s cannot get better cooling right now (owner, 2026-10-04), so heat is the hard limit and CPU capacity is not.

| Item | Value |
|---|---|
| How a pod waits | `job-template.yaml.tpl` creates every shard pod with `schedulingGates: [ci.cberg.home/thermal]`. A gated pod is `Pending` (`SchedulingGated`): the scheduler ignores it and it uses no node resources (it does count against the quota) |
| Who admits | `scripts/ninth-banner-admit.py`, one tick per poll (~10 s) of **every** running `ninth-banner-test.sh` (`COLLECT=0` runs stay until all their shards are admitted). A host-wide lock (`/tmp/ninth-banner-admit.lock`) lets one tick run at a time. It admits gated pods of **any** run, oldest first, at most one per node per tick: it pins the pod with `nodeSelector kubernetes.io/hostname=<node>`, removes the gate and annotates `ci.cberg.home/released-at` |
| A node is open when | 2-min average `x86_pkg_temp` **< 85 °C** (`GATE_OPEN_BELOW_C`) AND 3-min peak **< 93 °C** (`GATE_HOT_C`, the SOP target) AND **< 2 CI pods** bound or pinned there (`GATE_MAX_PER_NODE`) AND no CI start there for **300 s** (`GATE_SETTLE_SECONDS`; 120 s let nuc14-02 take a 2nd shard before the 1st one's heat showed) |
| Fail-closed | Missing or stale (> 90 s) Prometheus data closes the node. No trigger running means nothing is admitted (pods wait; `CIRunnerPodStuckPending` after 30 min) |
| Production | Never touched: the tick reads Prometheus and patches only gated pods in `ci-runner`. Running pods are never changed or evicted. `ci-low` CI pods can still be preempted by production |
| Status | `scripts/ninth-banner-admit.py --status` (node state + reason: `warm`/`hot`/`full`/`settling`, queue) |
| Mechanism choice | Pod scheduling gates admitted by the trigger. A cluster-scoped `MutatingAdmissionPolicy` + controller was the first design and was not approved (cluster-wide workload); node labels/taints were rejected (a taint would affect production, a label cannot hard-cap pods per node between controller ticks) |

Measured 2026-10-04 (nobody home; production 1.3-1.5 cores of container CPU per node; idle package 52-55 °C on nuc14-01/03, 62-76 °C on nuc14-02):

| | Before (13:13-15:13, quota 3 shards) | Trial (15:14-16:06, gate, quota 6) |
|---|---|---|
| Running CI pods (avg / max) | 2.85 / 3 | 3.2 / 5, never > 2 per node |
| Shards per hour | 30.5-31.5 | **35.8 (+15 %)** |
| Peak package temp n01 / n02 / n03 | 86 / 102 / 95 °C | 95 / 100 / **103** °C (single-sample turbo spikes) |
| Worst 2-min floor n01 / n02 / n03 | 73 / 87 / 85 °C | 88 / 94 / 92 °C (94 under the old 120 s settle) |
| Time at >= 93 °C n01 / n02 / n03 | 0 / 23 / 0.4 % | first 30 min: 3.3 / 16.7 / 10 %; last 30 min (300 s settle): 0 / 9 / 10 % |
| Time at >= 98 °C n02 | 13.8 % | first 30 min 8.3 %, last 30 min 1.7 % |
| Production restarts / OOM / evictions | 0 | 0 |

Reading: nuc14-02 is the hot node (it peaks at 96-98 °C with **no** CI pod: turbo bursts at ~1.7 busy cores), so the gate keeps CI off it most of the time and shifts the load to nuc14-01/03. Those are now admission-limited by the 2-per-node cap, not by heat.

CPU per shard (measured 2026-10-04): `sims` shards are single-threaded (~1.0 core, never throttled), so their limit is irrelevant. Browser shards (`release`, `responsive`, `e2e`) sit at their limit (CFS-throttled in 78-99 % of periods). A 3-CPU trial made a responsive shard take 272 s against a 207 s median at 4 CPU (+31 %) for the same CPU-seconds, so the default **stays 4**: fewer cores would cost throughput and not admit more pods.

Rollback triggers (watch during any change to these thresholds): any node with `min_over_time(node_thermal_zone_temp{type="x86_pkg_temp"}[2m]) >= 98` (>= 98 °C for 2 min), or a production restart/OOM/eviction. Neither fired in the trial.

---

## 3) Blueprints

Pod flow, one per shard:

```
init "clone"  (token mounted here only)          main "runner"  (no token)
  git fetch --depth 1 <full sha>  ->  /work/src  ->  npm ci -> suite shard -> /results/shard-N
                                                    echo CI-RESULT ... / CI-RESULTS-READY
                                                    wait <= 900s for /results/.collected
                                                    exit <suite rc>
trigger (Mac): poll logs -> kubectl cp /results -> touch .collected -> summary
```

Security model: the runner executes third-party code (npm install scripts, the game's tests). It therefore gets:
- no Kubernetes API token
- no cluster secrets in its namespace
- no reachable cluster or LAN destination
- no ingress
- the git credential only in the init container that runs nothing but `git fetch`

---

## 4) Operational Instructions

1. From the repo root on the Mac (as `mu`):
   ```bash
   scripts/ninth-banner-test.sh main unit
   scripts/ninth-banner-test.sh <sha> e2e 3
   scripts/ninth-banner-test.sh <sha> sims
   ```
2. The script resolves the ref to a full SHA (`gh api`), renders the template into `~/ci-results/<job>/job.yaml`, creates the Job, and prints one `CI-RESULT ...` line per shard as each finishes. It then copies the artifacts, prints `PASS`/`FAIL`, and exits 0 or 1.
3. Fire and forget: `COLLECT=0 scripts/ninth-banner-test.sh <sha> e2e`. Pods don't wait for collection; read the logs with `kubectl logs -n ci-runner -l batch.kubernetes.io/job-name=<job> -c runner --prefix`. Artifacts are lost when the pod exits.
4. Merged Playwright HTML report across shards: the script prints the `npx playwright merge-reports` command (needs `node_modules` in `~/code/the-ninth-banner`).
5. **Image bump** (whenever the game's `@playwright/test` changes; the tag MUST match it):
   ```bash
   V=1.64.0   # = package-lock.json node_modules/@playwright/test version
   curl -sI -H 'Accept: application/vnd.oci.image.index.v1+json' \
     https://mcr.microsoft.com/v2/playwright/manifests/v$V-noble | grep -i docker-content-digest
   ```
   Put `mcr.microsoft.com/playwright:v$V-noble@sha256:<that digest>` (the multi-arch **index** digest, not a per-arch one) into `job-template.yaml.tpl`, commit, then run `scripts/ninth-banner-test.sh main unit` and `... e2e 3` as the gate. No Flux reconcile is needed: the template is read by the trigger at run time.

---

## 5) Examples

```bash
# What is main right now?
gh api repos/nachtschatt3n/the-ninth-banner/commits/main --jq .sha

# Fewer Playwright workers per shard (e.g. flaky under load)
WORKERS=2 scripts/ninth-banner-test.sh main e2e 3

# Inspect a running job
kubectl get pods -n ci-runner -o wide
kubectl logs -n ci-runner <pod> -c clone
```

---

## 6) Verification Tests

1. Infra reconciled: `flux get ks -n flux-system the-ninth-banner-tests` is Ready, and `kubectl get resourcequota,limitrange,cnp,sa,cm,secret -n ci-runner` shows the objects.
2. Namespace hygiene: `kubectl get secret -n ci-runner` lists **only** `the-ninth-banner-git-credential`, with no `cluster-secrets` and no `sops-age`.
3. `scripts/ninth-banner-test.sh main unit` exits 0, and `~/ci-results/<job>/summary.txt` shows `result=PASS`.
4. `scripts/ninth-banner-test.sh main e2e 3` gives 3 shards on 3 different nodes (`kubectl get pods -o wide` while running) and a PASS summary, with `junit.xml` per shard.
5. Egress lockdown (while a runner pod is alive): `kubectl exec -n ci-runner <pod> -c runner -- node -e "fetch('https://example.com').then(()=>console.log('OPEN')).catch(()=>console.log('BLOCKED'))"` prints `BLOCKED`.
6. No-tests guard (since 2026-10-03): `SPECS="tests/e2e/smoke.spec.ts" scripts/ninth-banner-test.sh main e2e 1` prints `PASS` and `tests: N passed ... (executed N of N planned)` with N > 0; `SPECS="tests/e2e/does-not-exist.spec.ts" scripts/ninth-banner-test.sh main e2e 1` must exit 1 with `FAIL`. A browser suite that executed 0 tests is never green.

---

## 7) Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `clone` init fails with 403/404 | The credential cannot read the private repo, or the SHA was force-pushed away. Check the PAT scope (needs repo read). See Security Check |
| Pods `Pending` with status `SchedulingGated` | The thermal gate is holding them: every node is `warm`/`hot`/`full`/`settling`. `scripts/ninth-banner-admit.py --status` shows why. If no `ninth-banner-test.sh` is running, nothing admits them: start any run, or run `scripts/ninth-banner-admit.py` by hand (one tick) |
| nuc14-02 never gets a CI pod | Expected: it peaks at 96-98 °C even without CI, so its 3-min peak is usually >= 93 °C (§2b) |
| Pods `Pending`, event `exceeded quota` | Another run is still holding the quota (it waits up to 900s for collection). Wait, or delete the old Job |
| `npm ci` fails with `ENOTFOUND`/`ETIMEDOUT` | A package now resolves from a host other than `registry.npmjs.org`. Add that FQDN to `networkpolicy.yaml` after review |
| e2e timing tests fail (fps floor, clash fast-forward < 3000 ms, 120 s timeouts) while the pod sits at its 6-CPU limit | CPU oversubscription: Chromium renders in software here. Measured 2026-10-03 at `46eaae3`: `WORKERS=4` gave 3/3 shards FAIL (12 failed, 4 flaky, 14.6 min); `WORKERS=2` gave 77/77 passed, 0 flaky, 9.2 min. Keep 2 (the same per-worker CPU as GitHub's 4-vCPU runner) |
| NUCs at 100°C+, `NodeCPUTemperatureHigh` pending, etcd slow applies or a leader change during a run | Thermal: 3 shards × 6 CPU drove the nodes to 100-102°C on 2026-10-03, with an etcd leader election (102°C caused a thermal reboot on 2026-08-08, `docs/sops/immich.md`). The limit is 4 CPU per shard for this reason. **Never raise it without re-measuring** `max_over_time(node_thermal_zone_temp{type="x86_pkg_temp"}[30m])` during an e2e run (target < 93°C) |
| A red test run raises no alert | Expected since 2026-10-03: `KubeJobFailed` excludes `ci-runner` (a failing shard fails the Job by design) and `KubeCPUOvercommit` / `KubeMemoryOvercommit` (memory since 2026-10-04: 6 shards x 6Gi pushed the N-1 check over) ignore `ci-low` pods in `ci-runner` (preempted first on a node loss, so they do not use the N-1 headroom; a `ci-low` pod in any other namespace still counts). `KubeCPUQuotaOvercommit` / `KubeMemoryQuotaOvercommit` stay stock: they fire at quotas summing to > 1.5x allocatable and `ci-runner-quota` is ~0.2x. Also `KubeQuotaAlmostFull`/`KubeQuotaFullyUsed` exclude `ci-runner` (the quota is a cap runs fill by design). Runner INFRA faults alert instead: `CIRunnerPodStuckPending` (Pending > 15m: unschedulable, ImagePullBackOff, hung clone) `CIRunnerCloneFailed` (clone init container failed) and `CIRunnerJobStarved` (info: a run got no pod for 60m, e.g. quota held by an orphaned run). Rules: `kubernetes/apps/monitoring/kube-prometheus-stack/app/ci-runner-alerts.yaml` |
| npm/git `ENOTFOUND` or `EAI_AGAIN` after a policy change | The DNS allow-list (`networkpolicy.yaml`) is missing a name; Cilium REFUSES unlisted names |
| Log shows `GPU-FALLBACK` | The GPU slot was granted but the device/driver path failed (plugin or driver problem after a Talos/Mesa change) or the flags changed. (A pod requesting `gpu.intel.com/i915` cannot be scheduled without a slot; that case is `Pending`, below.) Check `kubectl describe pod` (resources), `kubectl get pods -n kube-system -l app.kubernetes.io/name=intel-gpu-plugin`, then rerun; `GPU=0` as the workaround |
| GPU shard `Pending`, event `Insufficient gpu.intel.com/i915` | All 5 iGPU slots on the candidate nodes are taken (media/frigate/immich). It waits; or run `GPU=0` |
| Shard OOMKilled | Lower `WORKERS`, or raise the runner memory limit in the template (keep the quota consistent) |
| A browser suite exits rc=2 at once | `GPU=0` was set (browser suites are GPU-only), or the ref predates the game's `tools/e2e-shard.ts` |
| `IMAGE MISMATCH` from the trigger | The game bumped Playwright: `tests/e2e/runner.json` at that ref names a different image. Bump `job-template.yaml.tpl` (§4 step 5) |
| `PASS` but `tests: 0 passed` / junit `tests="0"` (before 2026-10-03), now `NO-TESTS` in the shard log and `FAIL ... 0 tests executed` | Playwright exits 0 when the game's `--test-list` matches no test. Seen 2026-10-03 (`badbfd0`, `SPECS=tests/e2e/base-buildings.spec.ts`: 22 planned, 0 run, PASS): a `test.describe` title containing ` › ` (Playwright's title separator) makes the list line unmatchable. A wrong `SPECS` path or a `PROJECT` that selects nothing in a combined suite has the same effect. Both run.sh (per shard: planned from `shard-*.json` vs `<testcase>` count in `junit.xml`; rc=3) and the trigger (sum over all shards; exit 1) now fail such a run. Fix the title in the game, or the spec path |
| `TEST-COUNT-MISMATCH` warning (executed < planned) | Some planned tests never ran, same mechanism as above but partial (e.g. full runs silently dropped the 22 base-buildings tests). Advisory, not failing; the root cause is in the game repo (`tools/e2e-shard.ts` should refuse titles containing ` › ` and compare junit vs plan) |
| Script hangs on a shard | Check `kubectl describe pod`; the deadline is 90 min (`activeDeadlineSeconds`) |

---

## 8) Diagnose Examples

```bash
kubectl get jobs,pods -n ci-runner -o wide
kubectl describe job -n ci-runner <job>          # per-index failures
kubectl get events -n ci-runner --sort-by=.lastTimestamp | tail -20
# Cilium drops (egress lockdown working, or a missing FQDN)
kubectl -n kube-system exec ds/cilium -- cilium-dbg monitor --type drop
```

---

## 9) Health Check

- `flux get ks -n flux-system the-ninth-banner-tests` is Ready.
- `kubectl describe resourcequota -n ci-runner` shows usage at 0 when idle (no leaked Jobs; TTL is 1h).
- No pod older than 2h in `ci-runner`.

---

## 10) Security Check

- `kubectl get secret -n ci-runner` shows exactly one Secret (the git credential).
- `kubectl get rolebinding,role -n ci-runner` shows none (the thermal gate runs in the trigger on the Mac with the operator kubeconfig; it adds no in-cluster RBAC). The ServiceAccount has `automountServiceAccountToken: false`.
- The CiliumNetworkPolicy `ci-runner-lockdown` exists with `endpointSelector: {}`.
- **ACCEPTED RISK (owner, 2026-10-03; audit item W1):** the runner keeps the shared, account-wide `repo`-scoped GHCR PAT described below. The owner accepted the risk, mitigated by init-container-only mounting and the egress allow-list. Do not change the credential without a new owner decision. Re-evaluate when the PAT is rotated, or if the clone container ever runs anything besides `git fetch`. Register entry: see §10a.
- **Credential choice (owner decision 2026-10-03: reuse an existing token):** the runner reuses the shared GHCR pull PAT (the same ciphertext as `ghcr-the-ninth-banner` / arag-web, copied, never decrypted). The first clone (2026-10-03) proved it can read a **private repo's contents**, so it is not read:packages-only: it carries `repo` scope (classic PAT, account-wide, write-capable). The mitigations are structural: it is mounted only into the `clone` init container, which runs nothing but `git fetch`, and npm install scripts and tests run in a container that never has it. Least privilege would still be a read-only **deploy key** on `the-ninth-banner` alone (no expiry, one repo, read-only). Switch when convenient. Do NOT substitute the Flux git token or the MCP `GITHUB_TOKEN`, which are account-wide too.
- Egress verified 2026-10-03 from a live runner pod: `github.com` and `registry.npmjs.org` open; `example.com`, an in-cluster Service (Prometheus) and the LAN (Ollama host) blocked. The runner container has no `/secrets` mount and no token in env, and runs as uid 1001.

### 10a) Accepted-risk register entry (to be recorded by the operator)

The acceptance belongs in sweep_history `accepted_risks`. An agent prepared this and did NOT write it: the acceptance was relayed through an agent, and AR entries suppress findings. Run it after previewing the needle (`docs/sops/policy-cli.md`):

```bash
runbooks/policy-cli.py risk match --description 'ci-runner git credential'
runbooks/policy-cli.py risk add AR-<next> \
  --register-only register-only:posture \
  --severity medium \
  --description 'ci-runner git credential: shared account-wide repo-scoped GHCR PAT' \
  --justification 'Owner accepted 2026-10-03 (W1): mounted only in the clone init container (git fetch via GIT_ASKPASS), never in the test container; egress limited to github.com and registry.npmjs.org; no other cluster secrets in ci-runner. Least-privilege alternative (read-only deploy key or fine-grained PAT) deferred by the owner.' \
  --expires 2027-01-01
```

---

## 11) Rollback Plan

- **Thermal gate / caps (2026-10-04)**: `git revert` the quota commit (`feat(ci-runner): raise ninth-banner quota to 6 shards ...`) and push; Flux restores 3 shards. To remove the gate as well, also revert `feat(ci-runner): thermal gate ...` and `fix(ci-runner): thermal gate settle ...`, then release pods still gated by the old template: `scripts/ninth-banner-admit.py --release-all` (run it from the pre-revert checkout, or `kubectl patch` each gated pod's `spec.schedulingGates` to `[]`). Thresholds alone: edit the `GATE_*` defaults in `scripts/ninth-banner-admit.py`; they take effect on the next tick, no deploy.

- Stop runs: `kubectl delete jobs -n ci-runner --all`.
- Remove the runner: `git revert` the commit that added `kubernetes/apps/ci-runner/` and push. The namespace is annotated `prune: disabled`, so delete it by hand afterwards: `kubectl delete ns ci-runner`.

---

## 12) References

- `kubernetes/apps/ci-runner/`, `scripts/ninth-banner-test.sh`
- The game's `.github/workflows/ci.yml` (the suites mirrored here), `playwright.config.ts`
- `docs/sops/pod-security-admission.md`, `docs/sops/flux-image-automation-push-auth.md` (token classes)

---

## Version History

- `2026.10.03`: Initial runner: ci-runner namespace without `common`, restricted PSA, FQDN egress lockdown, indexed sharded Job template, one-command trigger with artifact collection.
- `2026.10.03` (hardening): image pinned by index digest + bump procedure; `PriorityClass ci-low` (-1000, never preempts); declared `default` SA without token; DNS allow-list instead of `*`; per-shard CPU 3/6 to 2/4 (requests/limits) after the nodes hit 100-102°C at 6 CPU; quota 6.5/13 CPU.
- `2026.10.03` (thermal/W1): at most 2 shards in parallel (thermal), runner declared best-effort (GitHub CI is the gate), shared-PAT risk recorded as owner-accepted (W1) with a prepared register entry.
- `2026.10.03` (GPU): GPU mode via the existing Intel GPU device plugin (shared `gpu.intel.com/i915`), default for e2e/nightly/responsive; browser-binary wrapper for the flags; renderer preflight; SPECS/PROJECT/CPU knobs; CPU vs GPU measurements.
- `2026.10.03` (GPU parallel): GPU residual risk accepted by the owner; GPU mode runs 3 shards in parallel (quota i915 cap 3); CPU mode stays at 2.
- `2026.10.03` (game hand-off `77764e6`): suites call the game's `test:*:shard` scripts with `E2E_OUT`; `e2e`/`responsive` GPU-only; new `release` suite + commit status `E2E (GPU, k8s)` posted from the Mac; image lockstep against `tests/e2e/runner.json`; runner-side browser wrapper removed.
- `2026.10.03` (release-all, game `4f26442`): `release` runs `test:release-all:shard` (release + responsive matrix as one pool over all shards, outputs in `shard-N/release/` and `shard-N/responsive/`); `E2E_RUNNER=k8s` exported for every suite; older refs keep the shard-1 responsive fallback.
- `2026.10.04` (thermal gate): shard pods created gated; `scripts/ninth-banner-admit.py` (ticked by every trigger) admits them onto nodes < 85 °C 2-min avg, < 93 °C 3-min peak, < 2 CI pods, 300 s settle; quota 3 -> 6 shards; `CIRunnerPodStuckPending` 15 -> 30 min; CPU per shard stays 4 (3-CPU trial: +31 % shard time). Trial: +15 % shards/h, no rollback trigger.
- `2026.10.03` (no-tests guard): a browser-suite shard with tests planned but 0 executed (or no plan at all, or 0 on a 1-shard run) fails with rc=3 (`NO-TESTS`); the trigger fails the run when the junit total is 0 (also posts `failure` for `release`) and warns on executed < planned; `CI-RESULT` carries `planned=`/`executed=`.
