# SOP: CI Runner — The Ninth Banner test suites as sharded Kubernetes Jobs

> Description: How The Ninth Banner's test suites (unit/check, Playwright e2e, responsive, simulation sweeps) run as ephemeral, sharded, locked-down Kubernetes Jobs in the `ci-runner` namespace, triggered with one command from the Mac mini, and how results are collected.
> Version: `2026.10.03`
> Last Updated: `2026-10-03`
> Owner: `homelab operator (cberg-home-nextgen)`

---

## 1) Description

The Mac mini also hosts the shared Ollama runtime and many agent sessions. Parallel Playwright runs drove its load to 110–170. This runner moves the game's test suites onto the three Talos nodes, which have plenty of idle CPU, while a namespace quota keeps production headroom.

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
| Trigger | `scripts/ninth-banner-test.sh <ref> <unit\|e2e\|nightly\|responsive\|sims> [shards]` |
| Image | `mcr.microsoft.com/playwright:v1.63.0-noble@sha256:eff16c30…` (multi-arch index digest; Node 24, git, Chromium/Firefox/WebKit baked in). **Keep in lockstep with `@playwright/test` in the game's `package-lock.json`**. Bump: §4 step 5 |
| Job shape | Indexed Job, `completions = shards`, `parallelism = min(shards, 3)`, `backoffLimitPerIndex: 0`, `maxFailedIndexes = shards` (no retries, one failing shard never stops the others), topology spread over `kubernetes.io/hostname`, `activeDeadlineSeconds: 5400`, `ttlSecondsAfterFinished: 3600` |
| Per shard | requests 2 CPU / 6Gi / 8Gi ephemeral; limits **4 CPU (thermal cap)** / 10Gi / 16Gi; Playwright `--workers=2` (`WORKERS`, default 2, see Troubleshooting) |
| Priority | `PriorityClass ci-low` (value -1000, `preemptionPolicy: Never`, cluster-scoped, in the app kustomization): CI pods never preempt production and are evicted first under node pressure |
| Quota | 4 pods, requests 6.5 CPU / 19Gi, limits 13 CPU / 32Gi; 0 Services, 0 PVCs. A second concurrent run queues (its shards are not created until quota frees) rather than squeezing production. `KubeQuotaAlmostFull`/`KubeQuotaFullyUsed` exclude `ci-runner` (the quota is a cap runs fill by design); `KubeQuotaExceeded` stays stock; a run starved by the quota raises `CIRunnerJobStarved` (info) after 60m |
| Egress | DNS (kube-dns, L7 DNS proxy) answering ONLY `github.com`, `registry.npmjs.org` and `**.cluster.local` (search-domain expansions); everything else REFUSED. TCP 443 to those two hosts only. Ingress: deny all. Both ServiceAccounts (`default` included) have `automountServiceAccountToken: false` |
| Credential | `the-ninth-banner-git-credential` (dockerconfigjson). Mounted **only** into the `clone` init container, read by `git-askpass.sh`; never in env, logs, or the test container |
| Results | `~/ci-results/<job>/` on the Mac: `summary.txt`, `shard-N.log`, `shard-N/{junit.xml, playwright-report/, test-results/ (traces), blob-report/, reports/, exit-code, commit}` |

Measured runtimes (2026-10-03, commit `46eaae3`, wall clock from the trigger):

| Run | Result | Wall time |
|---|---|---|
| `unit` (1 shard) | PASS, 38 files / 437 tests (+typecheck, lint, data, build, security) | 52 s incl. first image pull; suite 14 s |
| `e2e` 3 shards, `WORKERS=2` | PASS 77/77, 0 flaky, one shard per node | 9 min 10 s (longest shard 8.9 min) |
| `e2e` 3 shards, `WORKERS=4` | FAIL (CPU-starved timing tests) | 14 min 35 s |

Suites:

| Suite | What runs | Default shards |
|---|---|---|
| `unit` | `npm run check` (typecheck, lint, validate:data, vitest, build, security), the same as GitHub CI "Check & test" | 1 (forced) |
| `e2e` | `npm run build && npx playwright test --grep-invert "@art\|@nightly" --shard=i/N` (the game's per-push CI selection; Chromium plus Firefox `@cross`, `CI=1`, so 1 retry and no snapshot assertions) | 3 |
| `nightly` | `npm run build && npx playwright test --grep "@nightly\|@perf" --shard=i/N` (the game's nightly e2e job: determinism, music, perf specs) | 3 |
| `responsive` | `playwright test -c playwright.responsive.config.ts --shard=i/N` (WebKit). Fails with rc=2 until that config exists at the ref | 3 |
| `sims` | CI nightly sweeps (`sim --n 30 --check`, `gen-sweep --n 2000`, `autoplay --n 10 --check`, `ending-hunt --n 4`), round-robin over shards | 4 |

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

---

## 7) Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `clone` init fails with 403/404 | The credential cannot read the private repo, or the SHA was force-pushed away. Check the PAT scope (needs repo read). See Security Check |
| Pods `Pending`, event `exceeded quota` | Another run is still holding the quota (it waits up to 900s for collection). Wait, or delete the old Job |
| `npm ci` fails with `ENOTFOUND`/`ETIMEDOUT` | A package now resolves from a host other than `registry.npmjs.org`. Add that FQDN to `networkpolicy.yaml` after review |
| e2e timing tests fail (fps floor, clash fast-forward < 3000 ms, 120 s timeouts) while the pod sits at its 6-CPU limit | CPU oversubscription: Chromium renders in software here. Measured 2026-10-03 at `46eaae3`: `WORKERS=4` gave 3/3 shards FAIL (12 failed, 4 flaky, 14.6 min); `WORKERS=2` gave 77/77 passed, 0 flaky, 9.2 min. Keep 2 (the same per-worker CPU as GitHub's 4-vCPU runner) |
| NUCs at 100°C+, `NodeCPUTemperatureHigh` pending, etcd slow applies or a leader change during a run | Thermal: 3 shards × 6 CPU drove the nodes to 100-102°C on 2026-10-03, with an etcd leader election (102°C caused a thermal reboot on 2026-08-08, `docs/sops/immich.md`). The limit is 4 CPU per shard for this reason. **Never raise it without re-measuring** `max_over_time(node_thermal_zone_temp{type="x86_pkg_temp"}[30m])` during an e2e run (target < 93°C) |
| A red test run raises no alert | Expected since 2026-10-03: `KubeJobFailed` excludes `ci-runner` (a failing shard fails the Job by design) and `KubeCPUOvercommit` ignores `ci-low` pods, and `KubeQuotaAlmostFull`/`KubeQuotaFullyUsed` exclude `ci-runner` (the quota is a cap runs fill by design). Runner INFRA faults alert instead: `CIRunnerPodStuckPending` (Pending > 15m: unschedulable, ImagePullBackOff, hung clone) `CIRunnerCloneFailed` (clone init container failed) and `CIRunnerJobStarved` (info: a run got no pod for 60m, e.g. quota held by an orphaned run). Rules: `kubernetes/apps/monitoring/kube-prometheus-stack/app/ci-runner-alerts.yaml` |
| npm/git `ENOTFOUND` or `EAI_AGAIN` after a policy change | The DNS allow-list (`networkpolicy.yaml`) is missing a name; Cilium REFUSES unlisted names |
| Shard OOMKilled | Lower `WORKERS`, or raise the runner memory limit in the template (keep the quota consistent) |
| `responsive` rc=2 | `playwright.responsive.config.ts` is not in the repo at that ref yet |
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
- `kubectl get rolebinding,role -n ci-runner` shows none. The ServiceAccount has `automountServiceAccountToken: false`.
- The CiliumNetworkPolicy `ci-runner-lockdown` exists with `endpointSelector: {}`.
- **Credential choice (owner decision 2026-10-03: reuse an existing token):** the runner reuses the shared GHCR pull PAT (the same ciphertext as `ghcr-the-ninth-banner` / arag-web, copied, never decrypted). The first clone (2026-10-03) proved it can read a **private repo's contents**, so it is not read:packages-only: it carries `repo` scope (classic PAT, account-wide, write-capable). The mitigations are structural: it is mounted only into the `clone` init container, which runs nothing but `git fetch`, and npm install scripts and tests run in a container that never has it. Least privilege would still be a read-only **deploy key** on `the-ninth-banner` alone (no expiry, one repo, read-only). Switch when convenient. Do NOT substitute the Flux git token or the MCP `GITHUB_TOKEN`, which are account-wide too.
- Egress verified 2026-10-03 from a live runner pod: `github.com` and `registry.npmjs.org` open; `example.com`, an in-cluster Service (Prometheus) and the LAN (Ollama host) blocked. The runner container has no `/secrets` mount and no token in env, and runs as uid 1001.

---

## 11) Rollback Plan

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
