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
| Trigger | `scripts/ninth-banner-test.sh <ref> <unit\|e2e\|responsive\|sims> [shards]` |
| Image | `mcr.microsoft.com/playwright:v1.63.0-noble` (Node 24, git, Chromium/Firefox/WebKit baked in). **Keep in lockstep with `@playwright/test` in the game's `package-lock.json`** |
| Job shape | Indexed Job, `completions = shards`, `parallelism = min(shards, 3)`, `backoffLimitPerIndex: 0`, `maxFailedIndexes = shards` (no retries, one failing shard never stops the others), topology spread over `kubernetes.io/hostname`, `activeDeadlineSeconds: 5400`, `ttlSecondsAfterFinished: 3600` |
| Per shard | requests 3 CPU / 6Gi / 8Gi ephemeral; limits 6 CPU / 10Gi / 16Gi; Playwright `--workers=4` (`WORKERS`) |
| Quota | 4 pods, requests 9.5 CPU / 19Gi, limits 19 CPU / 32Gi; 0 Services, 0 PVCs. A second concurrent run queues (Pending) rather than squeezing production |
| Egress | DNS (kube-dns, L7 DNS proxy) + TCP 443 to `github.com` and `registry.npmjs.org` only. Ingress: deny all |
| Credential | `the-ninth-banner-git-credential` (dockerconfigjson). Mounted **only** into the `clone` init container, read by `git-askpass.sh`; never in env, logs, or the test container |
| Results | `~/ci-results/<job>/` on the Mac: `summary.txt`, `shard-N.log`, `shard-N/{junit.xml, playwright-report/, test-results/ (traces), blob-report/, reports/, exit-code, commit}` |

Suites:

| Suite | What runs | Default shards |
|---|---|---|
| `unit` | `npm run check` (typecheck, lint, validate:data, vitest, build, security), the same as GitHub CI "Check & test" | 1 (forced) |
| `e2e` | `npm run build && npx playwright test --grep-invert @art --shard=i/N` (Chromium plus Firefox `@cross`, `CI=1`, so 1 retry and no snapshot assertions) | 3 |
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
5. Playwright upgrade in the game: bump the image tag in `job-template.yaml.tpl` to the same `v<version>-noble`.

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
- **Credential choice:** the runner reuses the shared GHCR PAT (ciphertext copied, never decrypted). Least privilege would be a read-only **deploy key** on `the-ninth-banner` alone. Do NOT substitute the Flux git token or the MCP `GITHUB_TOKEN`: both are account-wide and write-capable, and this namespace runs third-party install scripts.

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
