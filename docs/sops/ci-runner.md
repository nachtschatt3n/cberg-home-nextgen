# SOP: CI Runner — The Ninth Banner test suites as sharded Kubernetes Jobs

> Description: How The Ninth Banner's test suites (unit/check, Playwright e2e, responsive, simulation sweeps) run as ephemeral, sharded, locked-down Kubernetes Jobs in the `ci-runner` namespace, triggered with one command from the Mac mini, and how results are collected; plus the self-hosted GitHub Actions runners (ARC, controller in `arc-system`, §2c).
> Version: `2026.10.06`
> Last Updated: `2026-10-06`
> Owner: `homelab operator (cberg-home-nextgen)`

---

## 1) Description

The Mac mini also hosts the shared Ollama runtime and many agent sessions. Parallel Playwright runs drove its load to 110–170. This runner moves the game's test suites onto the three Talos nodes, which have plenty of idle CPU, while a namespace quota keeps production headroom.

**Status: best-effort.** GitHub Actions CI stays the release gate. The runner is capped for node temperature: 4 CPU per shard, the namespace quota, nuc14-02 excluded, and the 35/55 W RAPL caps. The live thermal gate of 2026-10-04 (§2b) was removed on 2026-10-06.

- Scope: namespace `ci-runner`, Flux Kustomizations `flux-system/the-ninth-banner-tests` and `flux-system/the-ninth-banner-runners` (ARC scale set, §2c; controller `flux-system/gha-runner-scale-set-controller` in `arc-system`), trigger `scripts/ninth-banner-test.sh`, private repo `nachtschatt3n/the-ninth-banner`.
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
| Thermal gate | Removed 2026-10-06 (§2b). Shard pods are created ungated; the Job template's required node affinity excludes `k8s-nuc14-02`. |
| Job shape | Indexed Job, `completions = shards`, `parallelism = min(shards, 3)` in GPU mode, `min(shards, 2)` in CPU mode (**thermal cap**), `backoffLimitPerIndex: 0`, `maxFailedIndexes = shards` (no retries, one failing shard never stops the others), topology spread over `kubernetes.io/hostname` (placement is effectively the thermal gate's `nodeSelector` pin, §2b; parallelism is per Job, the total is the quota), `activeDeadlineSeconds: 5400`, `ttlSecondsAfterFinished: 600` (was 3600 until 2026-10-04; counts from the Job finishing, and every shard pod already holds until the trigger has copied its results, so 600 s is pure margin; with `COLLECT=0` it is the window to read failed shards' logs) |
| Per shard | requests 2 CPU / 6Gi / 8Gi ephemeral; limits **4 CPU (thermal cap)** / 10Gi / 16Gi; Playwright `--workers=2` (`WORKERS`, default 2, see Troubleshooting). emptyDir caps: `work` 10Gi, `tmp` 4Gi, **`results` 6Gi** (raised from 2Gi on 2026-10-04: the `release` shard holding the responsive screen tours (iPad/desktop screenshots) + perf specs was evicted twice with `Usage of EmptyDir volume "results" exceeds the limit "2Gi"` although all its tests passed; the other shards write 2-3 MB). Measured `work` is ~0.8Gi, so the unchanged 16Gi container limit still covers a full `results` dir (each node has 340Gi+ free for up to 2 shards per node / 6 in total). `run.sh` logs `results size:` plus the 10 largest entries (`du:` lines) right before `CI-RESULT`, so an oversize run shows what filled it |
| Priority | `PriorityClass ci-low` (value -1000, `preemptionPolicy: Never`, cluster-scoped, in the app kustomization): CI pods never preempt production and are evicted first under node pressure |
| Quota | **29 pods**, requests 58 CPU / 160Gi, limits 128 CPU / 280Gi, i915 13 (since 2026-10-06: 24 shard pods + 5 ARC runner pods sharing the namespace; 24 pods / 48 / 96 / i915 12 since 2026-10-04 evening; was 6 pods / 12 CPU / i915 6, before that 3 shards). Room for 12 running (gate cap) + 12 gated: gated pods count here, and with 6 a full queue of one lane kept the Job controller from creating the other lane's pods. The quota is only the TOTAL cap; per-node placement is the thermal gate's (§2b). 0 Services, 0 PVCs. Further runs queue (their shards are not created until quota frees) rather than squeezing production. `KubeQuotaAlmostFull`/`KubeQuotaFullyUsed` exclude `ci-runner` (the quota is a cap runs fill by design); `KubeQuotaExceeded` stays stock; a run starved by the quota raises `CIRunnerJobStarved` (info) after 60m |
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
| Sharing | Other GPU tenants per node (2026-10-03): nuc14-01 immich-server, jellyfin, makemkv (3/5); nuc14-02 frigate, plex (2/5); nuc14-03 scrypted, immich-ml (2/5). A CI shard is a short burst of WebGL; transcodes and detectors share the same iGPU time-sliced. If the pinned node has no free slot, the shard waits in Pending on that node until one frees (the gate does not check i915 slots) |
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
- The quota caps `requests.gpu.intel.com/i915` at 12 (one per browser shard, running + gated; since 2026-10-04 evening, was 6, before that 3; running GPU shards per node are capped only by the Mac-side thermal gate, §2b) and pins `gpu.intel.com/monitoring`, `i915_monitoring` and `npu.intel.com/accel` to 0, so a CI pod can never get the plugin's all-device monitoring resource or the NPU.
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
- Parallelism: per Job, **GPU mode runs up to 3 shards at once** (`parallelism`; owner decision 2026-10-03), CPU mode (`GPU=0`) 2. Across runs the quota allows 24 pods (running + queued), and the thermal gate (§2b) decides placement and the running count per node and lane. CPU cap per shard stays 4.
  Verified 2026-10-03 at `302a819`, 3 GPU shards in parallel (one per node, all on the Intel renderer): **3 min 54 s** wall time, 134/136 passed (1 flaky). Peak package temperatures 69 / 83 / 77 °C (nuc14-01/02/03), against 64 / 81 / 69 °C in the 10 min before. The failure is the known Firefox `music.spec` AudioContext issue (it fails on CPU too).
  `release` with `release-all` verified 2026-10-03 at game `4f26442`, 3 GPU shards: **6 min 57 s** wall time (was ~13 min with the whole responsive matrix on shard 1); shards 309 / 357 / 400 s test time; 188 passed, 0 failed, 26 skipped (3 flaky, passed on retry); status `E2E (GPU, k8s)` = success. Peak package temperatures 71 / 92 / 83 °C (nuc14-01/02/03) against 64 / 76 / 65 °C in the 10 min before; nuc14-02 is the warm node and touched 92 °C, just under the 93 °C target.


## 2b) Thermal gate (2026-10-04, REMOVED 2026-10-06)

> **REMOVED 2026-10-06 (owner decision).** No CI pod is created behind `ci.cberg.home/thermal` any more; the `arc-system/arc-thermal-gate` controller, its RBAC, `scripts/ninth-banner-admit.py`, its tests and the `CIRunnerThermalGateStalled` alert are deleted. What remains of the old policy: shard Jobs carry a required node affinity that excludes `k8s-nuc14-02`; the three ARC runner pools are limited to nuc14-01/03 by node affinity; the namespace quota, `ci-low` priority and the 35/55 W RAPL caps (Talos SysfsConfig) are the only limits on CI load and heat. The per-node CPU budget, the temperature thresholds and the 100 °C brake no longer exist. Revert path: `git revert` the two removal commits ("stop gating CI pods" and "remove the thermal gate controller"). The text below is kept as history and measurement record only; it does not describe live behaviour.

The quota only bounds the total; the gate used to decide **where and when** a shard started from each node's package temperature.

| Item | Value |
|---|---|
| How a pod waits | `job-template.yaml.tpl` creates every shard pod with `schedulingGates: [ci.cberg.home/thermal]`. A gated pod is `Pending` (`SchedulingGated`): the scheduler ignores it and it uses no node resources (it does count against the quota) |
| Who admits | `scripts/ninth-banner-admit.py`, one tick per poll (~10 s) of **every** running `ninth-banner-test.sh` (`COLLECT=0` runs stay until all their shards are admitted). **Run it as `mu`, never as root.** A host-wide lock (`/tmp/ninth-banner-admit.lock`, mu-owned `0644`, opened read-only with `O_NOFOLLOW`) lets one tick run at a time. It admits gated pods of **any** run, oldest first, at most one per node per tick: it pins the pod with `nodeSelector kubernetes.io/hostname=<node>`, removes the gate and annotates `ci.cberg.home/released-at` |
| Lanes (since 2026-10-04 evening) | Label `ci.cberg.home/lane` (set by `ninth-banner-test.sh`): **cpu** = `sims`/`unit` without GPU, requests 1 CPU / 1Gi / 2Gi disk, limits 1.5 CPU / 3Gi / 8Gi, no GPU (sims measured ~1.0 core, <= 0.61Gi; unit <= 1.2Gi, up to 3.5 cores, so it runs slower at 1.5); **browser** = everything else (2/4 CPU, 6/10Gi, i915 on GPU). Pods without the label: sims/unit without an i915 request count as cpu. Each lane is queued oldest first on its own: a closed lane never blocks the other |
| cpu lane open when | 2-min average **< 88 °C** (`GATE_CPU_OPEN_BELOW_C`) AND 3-min peak **< 96 °C** (`GATE_CPU_HOT_C`), **< 2 cpu-lane pods** on the node (`GATE_MAX_CPU_PER_NODE`; **< 1 on nuc14-02** since 2026-10-04 22:5x, `GATE_CPU_MAX_OVERRIDE=k8s-nuc14-02=1`: in the first per-node-brake watch it read 100 °C (2 samples, 22:44-22:45) with 2 sims pods admitted at 84/95 °C), on every node, independent of the browser slots |
| Every admission also needs | CI CPU **requests** on the node + the pod's <= **6** (`GATE_NODE_CPU_BUDGET`; owner: CI gets >= 6 CPU per node while it is below the thermal limits, e.g. 1 browser (2 req / 4 lim) + 2 sims, or 2 browser on nuc14-01), AND the pod's CPU/memory/i915 requests fit the node's allocatable minus all Pending/Running non-CI requests (kube-state-metrics) minus the CI pods there (reason `no room`; no capacity data = closed, fail-closed) AND the shared 300 s settle (any lane) |
| browser lane open when | **First CI pod** on the node: 2-min average `x86_pkg_temp` **< 88 °C** (`GATE_OPEN_BELOW_C`; raised from 85 on 2026-10-06 after the talos-sysfs-power-caps 24 h soak: temp p95 51/55/55 °C, max 62/75/71 °C, 0 min >= 100 °C, package throttles 88/1/14) AND 3-min peak **< 93 °C** (`GATE_HOT_C`, the SOP target). **Second CI pod**: 2-min average **< 78 °C** (`GATE_SECOND_OPEN_BELOW_C`) AND 3-min peak **< 90 °C** (`GATE_SECOND_HOT_C`); tightened 2026-10-04 after a 103 °C single sample on nuc14-03 with 2 shards (102 °C rebooted a node on 2026-08-08). A second pod is allowed **only on nuc14-01** (`GATE_SECOND_POD_NODES`): watch 2026-10-04 16:10-16:55, nuc14-03 passed the 78/90 °C pre-check (2-min avg ~75 °C, 3-min peak 84-88 °C), took a 2nd shard at 16:26 and read 102-103 °C two minutes later (the same happened at 15:32); the new shard's startup burst, not the pre-check temperature, causes the spike. nuc14-01 with 2 shards peaked at 92-95 °C; nuc14-02 reaches 96-100 °C with one shard or none. So nuc14-03 takes 1 CI pod, nuc14-01 up to 2 (total 3 while nuc14-02 is in `GATE_EXCLUDE_NODES`; 4 without the exclusion). Always: **< 2 CI pods** bound or pinned there (`GATE_MAX_PER_NODE`) AND no CI start there for **300 s** (`GATE_SETTLE_SECONDS`; 120 s let nuc14-02 take a 2nd shard before the 1st one's heat showed) |
| Brake (per node, since 2026-10-04 late evening) | A node whose package temperature reads **>= 100 °C** (`GATE_BRAKE_C`; i.e. its 1-min max) gets **no new CI pod** until **10 min** (`GATE_BRAKE_MINUTES`) after that reading (reason `brake` in `--status`). The other nodes keep admitting under their normal limits: a CI pod on one node does not heat another. **Global hold**: while **>= 2** nodes are braked at once (`GATE_GLOBAL_BRAKE_NODES`, 0 = never), i.e. two nodes read >= 100 °C within the same 10 min, nothing is admitted anywhere (a shared cause such as room heat or a cluster-wide burst; ends when the earlier brake expires). Stateless (computed from Prometheus each tick, so every trigger instance agrees). Running pods are never touched. Why per node: nuc14-02 alone reaches >= 100 °C in short turbo bursts from production load with no CI pod on it (27 of 360 min on 2026-10-04, 3 min in a quiet overnight window); under the old global brake each burst froze the whole farm for 10 min (22:32: 21-22 pods gated, 0 running, n01/n03 at 56/63 °C) |
| Excluded nodes (plan ci-runner-exclude-node02) | `GATE_EXCLUDE_NODES` (default `k8s-nuc14-02`): an excluded node takes **no** CI pod in either lane (reason `excluded` in `--status`), checked before every other limit. nuc14-02 hit 96 °C ~4 s into an 18-thread load at 35/55 W and logged ~65k package throttles in 7 days (01: 741, 03: 56): suspected cooler defect. Remove it from the default once the cooler is repaired/replaced. One-run override: `GATE_EXCLUDE_NODES= scripts/ninth-banner-test.sh ...` (empty = none excluded); it applies only to the ticks THAT trigger runs (the host lock is shared, concurrent triggers tick with their own env) |
| Fail-closed | Missing, stale (> 90 s) or non-finite Prometheus data closes the node. No trigger running means nothing is admitted (pods wait gated). `CIRunnerPodStuckPending` ignores `SchedulingGated` pods and gated pods count as Job-active (`CIRunnerJobStarved` does not see them), so **`CIRunnerThermalGateStalled`** (warning) covers it: gated pods exist AND no `ci-runner` pod was scheduled (newest `kube_pod_status_scheduled_time` = last release) for > 30 min, or no remaining `ci-runner` pod has a scheduled time (earlier ones TTL-deleted), held 5 min. The admitter exports no metric, so its liveness is read from its effect. N from live data 2026-10-04 (361 gated minutes, queue up to 24): release gap p50 1.9 / p90 7.4 / max 13.2 min (brake + settle). Tests: `runbooks/tests/test-ci-runner-gate-stalled-alert.py`. Without action the Job's `activeDeadlineSeconds` ends them. Check `--status` when it fires or a run seems stuck |
| Production | Never touched: the tick reads Prometheus and patches only gated pods in `ci-runner`. Running pods are never changed or evicted. `ci-low` CI pods can still be preempted by production |
| Pod slots (2026-10-04) | maxPods is 200 per node. Finished (Completed/Failed) pods do **not** use a slot: kubelet admission and the scheduler count only non-terminal pods, so the dashboard's pod percentage (all pods, terminal included) overstates the load. Measured 22:4x: active 108 / 71 / 108 of 200 on n01/n02/n03 (+18 gated CI pods, unscheduled). Finished CI pods are removed 600 s after their Job finishes (`ttlSecondsAfterFinished`, was 3600) |
| Status | `scripts/ninth-banner-admit.py --status` (per node and lane: `open` or reason `warm`/`hot` (with `2nd-pod limit` / `cpu lane`)/`full`/`budget`/`no room`/`settling`/`brake`, `BRAKE` lines per node, `GLOBAL HOLD` when >= 2 nodes are braked, queue with lanes). In the browser lane "second pod" means the node already has ANY CI pod, a sims pod included |
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

Tightened gate, watch 2026-10-04 16:10-16:55 (78/90 °C second-pod tier and brake, before the nuc14-01-only rule; real agent queue, then the queue emptied):

| | n01 | n02 | n03 |
|---|---|---|---|
| Peak package temp | 92 °C | 99 °C | **103 °C** (16:28-16:30, 2 shards; brake fired, admissions held ~10 min) |
| Worst 2-min floor | 80 °C | 80 °C | 84 °C |
| Time >= 93 °C / >= 98 °C | 0 / 0 % | 0 / 0 % | 0 / 0 % (single samples only) |

Throughput 30.1 shards/h in the busy window (incl. a 10-min brake stall), against 35.8 with the looser gate and 30.5-31.5 before the gate. Production: 0 restarts, OOMs or evictions. The nuc14-01-only second-pod rule was added after this watch and is not yet measured under load.

cpu lane, watch 2026-10-04 18:45-19:16 UTC (step 1 live: cpu lane, 6-CPU budget, quota 24; browser rules unchanged; real queue, 18-20 pods gated throughout):

| | n01 | n02 | n03 |
|---|---|---|---|
| Peak package temp (1-min max) | 84 °C | 94 °C | **99 °C** (1 browser + 2 sims, 18:50-18:52 and 19:08) |
| Worst 2-min average | 79 °C | 85 °C | 91 °C |
| Time >= 98 °C / samples >= 100 °C | 0 % / 0 | 0 % / 0 | 3.3 % / 0 |
| CI CPU requests running (avg / max) | 4.4 / 6 | 5.0 / 6 | 3.9 / 6 |
| CI cores actually used (avg) | 1.5 | 0.8 | 1.4 |

Throughput: **47.3 shards/h** (19.7 sims/unit + 27.6 browser) against ~25/h over the 2 h before (16-34/h per half hour) under the old gate. Brake never fired. Production: 0 restarts, OOMs, evictions or preemptions. Closed reasons (per node-lane sample): full 75, settling 55, warm 22, budget 16, hot 10.

Heat cost of a sims shard (12 h of 1-min data, 2026-10-04): a single-threaded shard runs one core at full turbo and costs about as much as a GPU browser shard. Node 2-min average with one sims pod vs none: n01 +12 °C, n02 +12 °C, **n03 +22 °C** (browser: +11/+13/+14). A pod start (either lane) lifts the 1-min peak a median +12-19 °C (p90 +22-32 °C) above the pre-start 2-min average; the first +10 °C shows after ~90-105 s (median), the peak after ~4.5-5.5 min, so the 300 s settle stays. n03 with 1 browser + 1 sims had a 1-min-max p90 of 101.6 °C before the lane existed. First step back if n03 reads >= 100 °C with the cpu lane: `GATE_MAX_CPU_PER_NODE` 1 for n03 (or lower `GATE_CPU_OPEN_BELOW_C` by 3 °C).

Not applied (pending owner approval): the owner's later "~98 °C" relaxation of the BROWSER lane (first pod 90/97 °C, second pod 87/96 °C, a second browser pod on every node). The browser lane keeps 85/93, 78/90 and nuc14-01-only.

Rollback triggers (watch during any change to these thresholds): any node with `min_over_time(node_thermal_zone_temp{type="x86_pkg_temp"}[2m]) >= 98` (>= 98 °C for 2 min), or a production restart/OOM/eviction. Neither fired in the trial.


## 2c) GitHub Actions runners (ARC, since 2026-10-06)

**Migration update, 2026-10-06:** The three-pool implementation and rollout steps are in [ninth-banner-actions-migration.md](ninth-banner-actions-migration.md). The original single-pool design below is historical. Fork PRs: the repository is private and gets no fork PRs. Keep *Fork pull request workflows* OFF, because the privileged Docker pool must not run unreviewed fork code; this supersedes the earlier same-day note authorizing fork PRs on all pools (owner, 2026-10-06). The owner also decided to reference the existing cluster token: each scale set's secret is a plain manifest with `github_token: "${GITHUB_TOKEN}"` filled by Flux substitution from `cluster-secrets` (a classic PAT; nothing copied or decrypted). The GitHub App design below remains the least-privilege option.

Self-hosted runners for the private repo `nachtschatt3n/the-ninth-banner`, so its GitHub CI can move off GitHub-hosted runners over time (a failed billing payment stopped every hosted job on 2026-10-05). They run next to the shard Jobs in `ci-runner`.

| Item | Value |
|---|---|
| Controller | `gha-runner-scale-set-controller` 0.15.0 in namespace **`arc-system`** (PSA restricted, no `common` component; Flux KS `flux-system/gha-runner-scale-set-controller`). `flags.watchSingleNamespace: ci-runner`: **no ClusterRole**; namespaced Roles in `arc-system` and `ci-runner` only (CRDs are cluster-scoped). Egress: DNS, kube-apiserver, `github.com`, `api.github.com`, `*.actions.githubusercontent.com`; ingress only from `monitoring` on :8080 |
| Scale set | `gha-runner-scale-set` 0.15.0, HelmRelease `ci-runner/the-ninth-banner-runners`, Flux KS `flux-system/the-ninth-banner-runners` (**listed but commented out** in `kubernetes/apps/ci-runner/kustomization.yaml` until the owner has written the secret). Scale set name `ninth-banner-k8s`, repo-scoped (`githubConfigUrl` = the repo) |
| runs-on labels | `ninth-banner-k8s` (the name, always matches) plus `self-hosted`, `ninth-banner`, `k8s`, `linux`, `x64`. Use `runs-on: [self-hosted, ninth-banner, k8s]`. Labels are registered only when the scale set is created; changing them means renaming `runnerScaleSetName` |
| Ephemeral | ARC JIT runners: one job per pod, pod deleted after the job. `ninth-banner-k8s` **`minRunners: 1`, `maxRunners: 4`**; build pool `ninth-banner-build-k8s` (`arc-build`) **`minRunners: 1`, `maxRunners: 2`**; browser pool `ninth-banner-browser-k8s` `0`/`1` (owner 2026-10-06: warm runners so a release's ~5 near-simultaneous jobs do not queue behind cold starts) |
| Placement | required node affinity `k8s-nuc14-01`/`k8s-nuc14-03` (nuc14-02 excluded, same as `GATE_EXCLUDE_NODES`). **No hard one-runner-per-node rule since 2026-10-06** (owner): pods of all three pools may share a node. **Per-node CI budget = the thermal gate**: every ARC pod is created gated and `arc-system/arc-thermal-gate` (`ninth-banner-admit.py --loop`, 10 s ticks) admits it only if the node's CI CPU requests stay <= 6 (`GATE_NODE_CPU_BUDGET`) and fit next to production, then pins it with `nodeSelector`, least-loaded node first (that is the spread). Requests are sized so the intended mix fits the 2 x 6 CPU: CPU runner 1.6, build pod 2.0, i.e. 2 runners + 1 build = 5.2 per node, all 6 pods 10.4 of 12, vs ~7.7 CPU production leaves free per node. A `preferred` pod anti-affinity (weight 100, same label) only spreads pods the scheduler places itself (gate rollback). `PriorityClass ci-low` |
| Pod | init `runner-agent` (`ghcr.io/actions/actions-runner:2.337.0@sha256:…`) copies the runner agent into an emptyDir; container `runner` runs it in the game's pinned Playwright image (same digest as `job-template.yaml.tpl`: Node 24, npm, git, browsers in `/ms-playwright`). uid/gid 1001, non-root, all caps dropped, read-only root FS, no privileged/hostPath, `automountServiceAccountToken: false` on the chart's `ninth-banner-k8s-gha-rs-no-permission` SA (no RBAC). No Docker: `services:`/`container:` jobs and `docker build` do not work here |
| Resources | runner requests **1.5 CPU** (+ postgres 0.1) / 2Gi / 2Gi disk, limits **6 CPU** (owner 2026-10-06; was 1/2, Vitest CPU-bound; bursts toward the limit accepted, node power caps are the backstop) / 6Gi / 16Gi; build pool (`arc-build`) dind/BuildKit requests **1.5** / limits 6 CPU, its runner container 0.5 / 2; LimitRange `max.cpu` 6 in both namespaces (test shards stay at 4 via the template); emptyDirs `runner` 12Gi, `home` 4Gi, `tmp` 4Gi. No GPU |
| Thermal | No gate since 2026-10-06 (§2b): the scheduler places ARC pods on nuc14-01/03 (node affinity); the RAPL caps are the heat limit. |
| Egress (runner pods) | `the-ninth-banner-runners-egress` adds to the namespace lockdown: `github.com`, `api.github.com`, `codeload.github.com`, `*.actions.githubusercontent.com`, `productionresultssa0`..`19.blob.core.windows.net` (log/artifact upload; exact names, no wildcard), `objects.githubusercontent.com`, `release-assets.githubusercontent.com`, `ghcr.io`, `pkg-containers.githubusercontent.com`, `registry.npmjs.org`. Not `nodejs.org`: skip `actions/setup-node` (Node 24 is in the image) |
| Credential | GitHub App (fallback: fine-grained PAT), secret `ci-runner/the-ninth-banner-arc-github` (`github_app_id`, `github_app_installation_id`, `github_app_private_key`), file `kubernetes/apps/ci-runner/the-ninth-banner-runners/app/github-app.sops.yaml`, **owner-written**. App permissions: Repository → Administration **Read and write** (needed to register repo-level runners), Metadata read; installed on this one repo only; webhook off. The controller copies it into `arc-system` for the listener; runner pods only get a per-job JIT config |
| Forks | Repo Settings → Actions → General → *Fork pull request workflows in private repositories*: keep **Run workflows from fork pull requests** OFF. Workflows from forks must never run on these runners |
| Observability | PodMonitor `arc-system/arc` (controller `gha_controller_*`, listener `gha_*`). Rules `gha-runner-scale-set-alerts.yaml`: `ARCPodNotReady`/`ARCPodCrashLooping` (critical), `ARCPodRestarted`, `ARCRunnerScaleSetNotRegistered` (secret present, no listener 15m), `ARCRunnerFailing` (failed ephemeral runners 10m), `ARCRunnerOutdated`, `ARCRunnerJobsWaiting` (30m). Runner pods Pending > 30m also fire `CIRunnerPodStuckPending`. `CIRunnerThermalGateStalled` ignores `ninth-banner-k8s-*` pods. Logs: Elasticsearch `logs-generic-default`, `k8s.namespace.name` `ci-runner` / `arc-system` |
| Upgrades | Known issue for the NEXT bump: ARC #4706 (0.14 -> 0.15 left old runner sets stuck Terminating); re-check the release notes before 0.15 -> 0.16. Controller + scale-set chart in lockstep (one commit; auto-update deny `*gha-runner-scale-set*`). Runner agent image must stay current: ARC disables self-update and GitHub stops assigning jobs to outdated runners (`ARCRunnerOutdated`) |

Residual risk (security review 2026-10-06, W2): the App's Administration read-write on the repo is required for repo-level runners, but a leaked key could change repo settings or delete the repo. Mitigations: one repo only, webhook off, key only in SOPS + the controller/listener namespaces (no runner pod sees it), rotate by generating a new App key, `sops` edit, then revoke the old key. Egress to GHCR/api.github.com/npm/blob can still carry data out via attacker-owned accounts while those hosts are allowed. Register entry (operator runs it, an agent did not):
```bash
runbooks/policy-cli.py risk add AR-<next> --register-only register-only:posture --severity medium \
  --description 'ci-runner ARC GitHub App: Administration RW on the-ninth-banner; runner egress to GitHub/GHCR/npm/Actions blob' \
  --justification 'Owner-requested self-hosted runners 2026-10-06; App installed on one repo, webhook off, key never in runner pods, ephemeral non-root runners, no fork PR workflows, exact-name egress allow-list.' \
  --expires 2027-01-01
```

Enable (owner): fill the secret with `sops`, uncomment `- ./the-ninth-banner-runners/ks.yaml` in `kubernetes/apps/ci-runner/kustomization.yaml`, commit both with `git commit --only`, push. Verify: `kubectl -n ci-runner get autoscalingrunnerset` shows the set, `kubectl -n arc-system get pods` shows `arc-controller-*` and `ninth-banner-k8s-*-listener` Running, and the repo's Settings → Actions → Runners lists `ninth-banner-k8s`.

Disable: comment the line again and push (Flux prunes the scale set; the controller deregisters it). Remove ARC entirely: also `git revert` the commit that added `kubernetes/apps/arc-system/`, then `kubectl delete ns arc-system` (prune disabled) and the `actions.github.com` CRDs by hand.

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
2. Namespace hygiene: `kubectl get secret -n ci-runner` lists `the-ninth-banner-git-credential` (plus the ARC secrets of §2c once enabled), with no `cluster-secrets` and no `sops-age`.
3. `scripts/ninth-banner-test.sh main unit` exits 0, and `~/ci-results/<job>/summary.txt` shows `result=PASS`.
4. `scripts/ninth-banner-test.sh main e2e 3` gets all 3 shards admitted (no `ci.cberg.home/thermal` gate left), never more than 2 CI pods per node (`kubectl get pods -o wide` while running), and a PASS summary, with `junit.xml` per shard.
5. Egress lockdown (while a runner pod is alive): `kubectl exec -n ci-runner <pod> -c runner -- node -e "fetch('https://example.com').then(()=>console.log('OPEN')).catch(()=>console.log('BLOCKED'))"` prints `BLOCKED`.
6. No-tests guard (since 2026-10-03): `SPECS="tests/e2e/smoke.spec.ts" scripts/ninth-banner-test.sh main e2e 1` prints `PASS` and `tests: N passed ... (executed N of N planned)` with N > 0; `SPECS="tests/e2e/does-not-exist.spec.ts" scripts/ninth-banner-test.sh main e2e 1` must exit 1 with `FAIL`. A browser suite that executed 0 tests is never green.

---

## 7) Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `clone` init fails with 403/404 | The credential cannot read the private repo, or the SHA was force-pushed away. Check the PAT scope (needs repo read). See Security Check |
| Pods `Pending` with status `SchedulingGated` | Should not occur since 2026-10-06 (gate removed, §2b). If one appears, something re-added `ci.cberg.home/thermal`; nothing releases it, so delete the pod or remove the gate from the template. |
| nuc14-02 never gets a CI pod | Expected: the shard Job template excludes it with a required node affinity and the ARC pools only allow nuc14-01/03 (suspected cooler defect) |
| Pods `Pending`, event `exceeded quota` | Another run is still holding the quota (it waits up to 900s for collection). Wait, or delete the old Job |
| `npm ci` fails with `ENOTFOUND`/`ETIMEDOUT` | A package now resolves from a host other than `registry.npmjs.org`. Add that FQDN to `networkpolicy.yaml` after review |
| e2e timing tests fail (fps floor, clash fast-forward < 3000 ms, 120 s timeouts) while the pod sits at its 6-CPU limit | CPU oversubscription: Chromium renders in software here. Measured 2026-10-03 at `46eaae3`: `WORKERS=4` gave 3/3 shards FAIL (12 failed, 4 flaky, 14.6 min); `WORKERS=2` gave 77/77 passed, 0 flaky, 9.2 min. Keep 2 (the same per-worker CPU as GitHub's 4-vCPU runner) |
| NUCs at 100°C+, `NodeCPUTemperatureHigh` pending, etcd slow applies or a leader change during a run | Thermal: 3 shards × 6 CPU drove the nodes to 100-102°C on 2026-10-03, with an etcd leader election (102°C caused a thermal reboot on 2026-08-08, `docs/sops/immich.md`). The limit is 4 CPU per shard for this reason. **Never raise it without re-measuring** `max_over_time(node_thermal_zone_temp{type="x86_pkg_temp"}[30m])` during an e2e run (target < 93°C) |
| A red test run raises no alert | Expected since 2026-10-03: `KubeJobFailed` excludes `ci-runner` (a failing shard fails the Job by design) and `KubeCPUOvercommit` / `KubeMemoryOvercommit` (memory since 2026-10-04: 6 shards x 6Gi pushed the N-1 check over) ignore `ci-low` pods in `ci-runner` (preempted first on a node loss, so they do not use the N-1 headroom; a `ci-low` pod in any other namespace still counts). `KubeCPUQuotaOvercommit` / `KubeMemoryQuotaOvercommit` stay stock: they fire at quotas summing to > 1.5x allocatable and `ci-runner-quota` is ~0.2x. Also `KubeQuotaAlmostFull`/`KubeQuotaFullyUsed` exclude `ci-runner` (the quota is a cap runs fill by design). Runner INFRA faults alert instead: `CIRunnerPodStuckPending` (Pending > 30m after the thermal gate released the pod: unschedulable, ImagePullBackOff, hung clone, missing ConfigMap/Secret; gated pods are excluded via `kube_pod_status_reason{reason="SchedulingGated"}`, tests: `runbooks/tests/test-ci-runner-pending-alert.py`), `CIRunnerThermalGateStalled` (gated pods but no gate release for 30m, fires after a further 5m hold: admitter dead/wedged or gate held closed, §2b Fail-closed), `CIRunnerCloneFailed` (clone init container failed) and `CIRunnerJobStarved` (info: a run got no pod for 60m, e.g. quota held by an orphaned run). Rules: `kubernetes/apps/monitoring/kube-prometheus-stack/app/ci-runner-alerts.yaml` |
| npm/git `ENOTFOUND` or `EAI_AGAIN` after a policy change | The DNS allow-list (`networkpolicy.yaml`) is missing a name; Cilium REFUSES unlisted names |
| Log shows `GPU-FALLBACK` | The GPU slot was granted but the device/driver path failed (plugin or driver problem after a Talos/Mesa change) or the flags changed. (A pod requesting `gpu.intel.com/i915` cannot be scheduled without a slot; that case is `Pending`, below.) Check `kubectl describe pod` (resources), `kubectl get pods -n kube-system -l app.kubernetes.io/name=intel-gpu-plugin`, then rerun; `GPU=0` as the workaround |
| GPU shard `Pending`, event `Insufficient gpu.intel.com/i915` | All 5 iGPU slots on the pinned node are taken (the thermal gate pins without checking i915 slots) (media/frigate/immich). It waits; or run `GPU=0` |
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

- `kubectl get secret -n ci-runner` shows the git credential and, once ARC is enabled (§2c), `the-ninth-banner-arc-github` plus ARC's per-runner JIT secrets; never `cluster-secrets` or `sops-age`.
- `kubectl get rolebinding,role -n ci-runner` shows only ARC's (§2c): `arc-controller-single-namespace-watch`, `ninth-banner-k8s-gha-rs-manager` and the listener Role, all bound to ServiceAccounts in `arc-system`. No ServiceAccount in `ci-runner` has a binding (the thermal gate runs on the Mac with the operator kubeconfig). Every pod has `automountServiceAccountToken: false`.
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

- **Per-node brake (2026-10-04 late evening)**: `git revert <per-node brake commit>` and push; the old global brake applies on the next tick (script runs on the Mac, no Flux step). Without a revert, `GATE_GLOBAL_BRAKE_NODES=1` in the trigger's environment restores the global brake.
- **cpu lane / quota 24 (2026-10-04 evening)**: `git revert c0405efc` and push (gate, template, runner and quota together; Flux restores the 6-pod quota, the gate change applies on the next tick). Gated pods created from the new template keep their small requests and are admitted by the old gate as ordinary CI pods. Do NOT run `--release-all` with the 24-pod quota still live: it would release up to 24 pods unpinned.
- **Thermal gate / caps (2026-10-04)**: `git revert` the quota commit (`feat(ci-runner): raise ninth-banner quota to 6 shards ...`) and push; Flux restores 3 shards. To remove the gate as well, also revert `feat(ci-runner): thermal gate ...` and `fix(ci-runner): thermal gate settle ...`, then release pods still gated by the old template: `scripts/ninth-banner-admit.py --release-all` (run it from the pre-revert checkout, or `kubectl patch` each gated pod's `spec.schedulingGates` to `[]`). Thresholds alone: edit the `GATE_*` defaults in `scripts/ninth-banner-admit.py`; they take effect on the next tick, no deploy.

- Stop runs: `kubectl delete jobs -n ci-runner --all`.
- Remove the runner: `git revert` the commit that added `kubernetes/apps/ci-runner/` and push. The namespace is annotated `prune: disabled`, so delete it by hand afterwards: `kubectl delete ns ci-runner`.

---

## 12) References

- `kubernetes/apps/ci-runner/`, `scripts/ninth-banner-test.sh`, `scripts/ninth-banner-admit.py` (thermal gate)
- `kubernetes/apps/monitoring/kube-prometheus-stack/app/ci-runner-alerts.yaml`
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
- `2026.10.03` (no-tests guard): a browser-suite shard with tests planned but 0 executed (or no plan at all, or 0 on a 1-shard run) fails with rc=3 (`NO-TESTS`); the trigger fails the run when the junit total is 0 (also posts `failure` for `release`) and warns on executed < planned; `CI-RESULT` carries `planned=`/`executed=`.
- `2026.10.04` (thermal gate): shard pods created gated; `scripts/ninth-banner-admit.py` (ticked by every trigger) admits them onto nodes < 85 °C 2-min avg, < 93 °C 3-min peak, < 2 CI pods, 300 s settle; quota 3 -> 6 shards; `CIRunnerPodStuckPending` 15 -> 30 min; CPU per shard stays 4 (3-CPU trial: +31 % shard time). Trial: +15 % shards/h, no rollback trigger.
- `2026.10.04` (also same day): results emptyDir 2Gi -> 6Gi (`7af2cf37`); `KubeMemoryOvercommit` ignores preemptible ci-runner pods (`a0d9cbe0`).
- `2026.10.04` (tightened gate): second CI pod on a node needs 2-min avg < 78 °C and 3-min peak < 90 °C, and only nuc14-01 may take one (nuc14-03 hit 103 °C twice after a 2nd shard); brake: no admissions anywhere for 10 min after any node reads >= 100 °C; non-finite temperatures close the node; lock file mu-owned 0644, `O_NOFOLLOW`; stale doc/header drift fixed (doc-agent review).
- `2026.10.04` (cpu lane): sims/unit get their own lane (1/1.5 CPU, 1/3Gi, no GPU; up to 2 per node below 88 °C 2-min avg / 96 °C 3-min peak); CI CPU requests <= 6 per node + allocatable fit check; quota 6 -> 24 pods, i915 6 -> 12; heat cost of a sims shard measured (+12 to +22 °C, about a GPU browser shard). Browser thresholds unchanged: the owner-requested relaxation (90/97 °C, 2nd browser pod on every node) was NOT applied, it is pending explicit owner approval. Watch: 18:45-19:16 UTC, 47.3 shards/h (from ~25/h), peaks 84/94/99 °C, no >= 100 °C sample, no production impact.
- `2026.10.04` (per-node brake): a node reading >= 100 °C is braked alone for 10 min (reason `brake`); others keep admitting; global hold only while >= 2 nodes are braked (`GATE_GLOBAL_BRAKE_NODES`). nuc14-02's production-only spikes no longer freeze the farm.
- `2026.10.04` (Job TTL): `ttlSecondsAfterFinished` 3600 -> 600 (pods already hold until collected, so no result loss); pod-slot note in §2b (terminal pods use no maxPods slot).
- `2026.10.04` (n02 cpu cap): nuc14-02 takes at most 1 cpu-lane pod (`GATE_CPU_MAX_OVERRIDE`); it read 100 °C with 2 sims pods once the global brake no longer kept it idle.
- `2026.10.04` (gated-pod alert fix): `CIRunnerPodStuckPending` no longer counts thermal-gated pods (fired for all 16 gated pods ~20:37 UTC); the 30 min timer starts at release. Gap recorded: a dead admitter is now unalerted.
- `2026.10.04` (gate-stall alert): new `CIRunnerThermalGateStalled` (warning) closes that gap: gated pods + no pod scheduled in `ci-runner` for > 30 min (or no remaining pod has a scheduled time), `for: 5m`; promtool cases + 5 mutants in `runbooks/tests/test-ci-runner-gate-stalled-alert.py`; would not have fired once in the first day of gate data (max release gap 13.2 min).
- `2026.10.06` (node exclusion): `GATE_EXCLUDE_NODES` (default `k8s-nuc14-02`) keeps CI off nuc14-02 in both lanes until its cooling is fixed (plan ci-runner-exclude-node02).
- `2026.10.06` (power caps soak): `GATE_OPEN_BELOW_C` 85 -> 88 °C (browser lane, first pod only; HOT 93, second-pod, cpu-lane and brake limits unchanged). Evidence from the 35/55 W caps' 24 h soak: p95 51/55/55 °C, max 62/75/71 °C, 0 minutes >= 100 °C, throttles 88/1/14; Phase C CI max 62/70/71 °C. Plan talos-sysfs-power-caps §3.10.
- `2026.10.06` (ARC runners): §2c: actions-runner-controller 0.15.0 (`arc-system`, single-namespace RBAC) + repo-scoped ephemeral scale set `ninth-banner-k8s` in `ci-runner` (max 2, nuc14-01/03, one per node, non-browser jobs only); admitter counts runner pods as cpu-lane CI pods; `CIRunnerThermalGateStalled` ignores runner pods; new `gha-runner-scale-set-alerts.yaml`. Scale set off until the owner writes the GitHub App secret.
- `2026.10.06` (ARC warm runners, shared nodes): `ninth-banner-k8s` min 1 / max 4, `ninth-banner-build-k8s` min 1 / max 2 (browser pool unchanged except its anti-affinity); required one-runner-per-node anti-affinity replaced by a preferred spread in all three pools (a required term on the shared label would block every pool on nodes holding a warm runner); per-node budget = the gate's existing 6-CPU `GATE_NODE_CPU_BUDGET` with requests resized (runner 2 -> 1.5, dind 2 -> 1.5, build runner 1 -> 0.5); admitter: warm idle runners keep budget/capacity/tier but free their lane slot (new Role rule `ephemeralrunners` get/list), gate Deployment rolled via `ci.cberg.home/script-rev`; `ci-runner` quota +5 pods (29) for the runner pods. No thermal threshold, settle, brake, node exclusion or `ci-low` change.
- `2026.10.06` (ARC 6 CPU): `ninth-banner-k8s` runner and `ninth-banner-build-k8s` dind 2/6 CPU request/limit (were 1/2); LimitRange max cpu 4 -> 6 in `ci-runner` and `arc-build`. Thermal gate, its thresholds, the 6-CPU node budget, one-runner-per-node and the nuc14-02 exclusion unchanged.

- `2026.10.06` (gate removed): owner decision. `ci.cberg.home/thermal` schedulingGates dropped from the shard Job template and the three ARC scale sets; `arc-system/arc-thermal-gate`, its RBAC, `scripts/ninth-banner-admit.py`, its tests and `CIRunnerThermalGateStalled` deleted. Shard Jobs exclude nuc14-02 by node affinity. The 35/55 W RAPL caps are the only heat limit.
