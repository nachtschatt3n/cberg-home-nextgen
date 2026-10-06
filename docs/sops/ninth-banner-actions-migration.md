# The Ninth Banner GitHub Actions on Kubernetes

Status: **enabling (2026-10-06)**. Three ARC runner scale sets replace every GitHub-hosted job once Flux substitutes the existing cluster `GITHUB_TOKEN` into their secrets and the Flux Kustomizations are enabled. **No fork PRs (owner, 2026-10-06):** the repository is private and nobody forks it, so fork-PR tests are not part of this rollout. Keep *Fork pull request workflows* OFF in the repository settings (Settings → Actions → General); the privileged Docker pool must not run unreviewed fork code. This supersedes the earlier same-day note that authorized fork PRs on all pools.

| Scale set | Namespace | Jobs | Capacity |
|---|---|---|---|
| `ninth-banner-k8s` | `ci-runner` | check, nightly sweeps, nightly report, release gate dry run | 0-2 |
| `ninth-banner-browser-k8s` | `ci-runner` | art, responsive, nightly E2E | 0-1, Intel iGPU |
| `ninth-banner-build-k8s` | `arc-build` | image, release | 0-1, privileged Docker-in-Docker |

Runner pods are placed by the scheduler on nuc14-01/03 only (node affinity); the thermal gate (`ci.cberg.home/thermal`) was removed 2026-10-06. The build namespace has its own ARC controller and restricted egress. The Docker sidecar is privileged, so the runner's `GITHUB_TOKEN` and any public network endpoint available to a job are exposed to whatever code the job builds. That is why fork PR workflows stay off (see above). The earlier owner acceptance of fork code on these pools is superseded.

## Credential and enablement

Owner decision 2026-10-06: **reference** the GitHub token that is already in the cluster. Do not create, copy or decrypt any credential. The two ARC secrets are plain manifests with no value in git:

- `kubernetes/apps/ci-runner/the-ninth-banner-runners/app/github-token.yaml` (`the-ninth-banner-arc-github`, used by `ninth-banner-k8s` and `ninth-banner-browser-k8s`)
- `kubernetes/apps/arc-build/the-ninth-banner-build-runners/app/github-token.yaml` (`the-ninth-banner-arc-build-github`, used by `ninth-banner-build-k8s`)

Each contains `github_token: "${GITHUB_TOKEN}"`. The scale-set Flux Kustomizations live in `flux-system`, and `kubernetes/flux/cluster/ks.yaml` patches every child Kustomization with `postBuild.substituteFrom: cluster-secrets`, so Flux fills the value at apply time. Never set `kustomize.toolkit.fluxcd.io/substitute: disabled` on these app directories, and escape any future literal `${...}` in them as `$${...}`. The token is a **classic PAT**. To register repository scale sets it needs admin on `nachtschatt3n/the-ninth-banner` (classic `repo` scope). Rotating `GITHUB_TOKEN` rotates ARC too. A repo-scoped GitHub App (Administration read/write, Metadata read; keys `github_app_id`, `github_app_installation_id`, `github_app_private_key`) remains the least-privilege option. The materialized Secret exists in `ci-runner` and `arc-build`, and ARC copies it into `arc-system` for the listener. Runner pods set `automountServiceAccountToken: false` and cannot read it.

To disable the cluster runners, comment the three scale-set entries in `kubernetes/apps/ci-runner/kustomization.yaml` and `kubernetes/apps/arc-build/kustomization.yaml`. Verify `flux get ks -A`, `kubectl get autoscalingrunnersets -A`, listener/controller pods in `arc-system`, and all three sets in GitHub repository Settings → Actions → Runners.

## Deployment test sequence

1. Validate Kustomize output for both controllers, the test infrastructure and all three scale sets. Validate the Helm chart's rendered `AutoscalingRunnerSet` Pod templates: CPU has Postgres, browser requests `gpu.intel.com/i915:1`, build has the pinned privileged Docker sidecar with resources, and all runner templates have `schedulingGates`.
2. After Flux reports Ready, trigger a harmless `workflow_dispatch` on the game branch. Watch each pod go pending → running → removed. Confirm nothing lands on nuc14-02 and one build runner occupies at most one node.
3. Run a branch push/PR check, a same-repo PR image build, the manual responsive and nightly Playwright jobs, a manual image build, and the release gate dry run. Inspect `gh run view <id> --log-failed` and the matching runner/listener pods. Confirm Postgres connection, GPU assertion, Docker build + smoke, GitHub CLI install, artifact upload, and GHCR permissions. Run a release only with the normal release approval and tag process. Fork-PR tests do not apply (private repo, fork workflows off).
4. Confirm no job has `runs-on: ubuntu-latest`, no hosted runner minutes were used for these workflows, pods and JIT secrets are removed after each run, no production restarts/OOM/evictions occurred, and package temperatures remain under the existing `ci-runner` SOP thresholds. Check the ARC and CI alerts.

Keep the scale sets disabled if any credential, policy, scheduling or first-run check fails. Roll back the workflow changes to restore hosted routing only when GitHub billing permits it; otherwise fix or disable the affected scale set. To disable the cluster runners, comment the three scale set entries and reconcile Flux after active jobs finish. The existing Mac-triggered Kubernetes test Jobs remain available while the GitHub Actions migration is tested.
