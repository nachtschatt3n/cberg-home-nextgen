# The Ninth Banner GitHub Actions on Kubernetes

Status: **prepared, not enabled**. Three ARC runner scale sets replace every GitHub-hosted job after a repository-scoped fine-grained PAT is installed and the Flux Kustomizations are enabled. This runbook records the 2026-10-06 owner decision to run fork PRs on the cluster, including privileged Docker image builds.

| Scale set | Namespace | Jobs | Capacity |
|---|---|---|---|
| `ninth-banner-k8s` | `ci-runner` | check, nightly sweeps, nightly report, release gate dry run | 0-2 |
| `ninth-banner-browser-k8s` | `ci-runner` | art, responsive, nightly E2E | 0-1, Intel iGPU |
| `ninth-banner-build-k8s` | `arc-build` | image, release | 0-1, privileged Docker-in-Docker |

All runner pods start behind `ci.cberg.home/thermal`; `arc-system/arc-thermal-gate` admits them on nuc14-01/03 using Prometheus temperatures and node headroom. The build namespace has its own ARC controller and restricted egress. The Docker sidecar is privileged; the runner's `GITHUB_TOKEN` and any public network endpoint available to the job must be treated as exposed to fork PR code. The owner explicitly accepted that risk for this repository on 2026-10-06. Do not add high-value repository secrets to fork PR jobs.

## Credential and enablement

Create a **fine-grained PAT** scoped only to `nachtschatt3n/the-ninth-banner` with repository **Administration: read and write**. It is required to register repository runner scale sets; it is not injected into runner jobs. Put it in the `github_token` field of both SOPS secrets:

- `kubernetes/apps/ci-runner/the-ninth-banner-runners/app/github-token.sops.yaml`
- `kubernetes/apps/arc-build/the-ninth-banner-build-runners/app/github-token.sops.yaml`

The checked-in encrypted value is a placeholder. Never enable a scale set while it remains. Decrypt locally to verify the value, without printing it or committing plaintext. Then uncomment the three scale set `ks.yaml` entries in `kubernetes/apps/ci-runner/kustomization.yaml` and `kubernetes/apps/arc-build/kustomization.yaml`, commit and push the cluster branch. The ARC controllers, thermal gate, namespace and RBAC may reconcile first. Verify `flux get ks -A`, `kubectl get autoscalingrunnersets -A`, listener/controller pods in `arc-system`, and all three sets in GitHub repository Settings → Actions → Runners.

## Deployment test sequence

1. Validate Kustomize output for both controllers, the test infrastructure and all three scale sets. Validate the Helm chart's rendered `AutoscalingRunnerSet` Pod templates: CPU has Postgres, browser requests `gpu.intel.com/i915:1`, build has the pinned privileged Docker sidecar with resources, and all runner templates have `schedulingGates`.
2. After Flux reports Ready, trigger a harmless `workflow_dispatch` on the game branch. Watch gated → admitted → running → removed for each pod. Confirm the thermal gate never admits on nuc14-02 and one build runner occupies at most one node.
3. Run a branch push/PR check, a fork PR check, a fork PR image build, the manual responsive and nightly Playwright jobs, a manual image build, and the release gate dry run. Inspect `gh run view <id> --log-failed` and the matching runner/listener pods. Confirm Postgres connection, GPU assertion, Docker build + smoke, GitHub CLI install, artifact upload, and GHCR permissions. Run a release only with the normal release approval and tag process.
4. Confirm no job has `runs-on: ubuntu-latest`, no hosted runner minutes were used for these workflows, pods and JIT secrets are removed after each run, no production restarts/OOM/evictions occurred, and package temperatures remain under the existing `ci-runner` SOP thresholds. Check the ARC and CI alerts.

Keep the scale sets disabled if any credential, policy, scheduling or first-run check fails. Roll back the workflow changes to restore hosted routing only when GitHub billing permits it; otherwise fix or disable the affected scale set. To disable the cluster runners, comment the three scale set entries and reconcile Flux after active jobs finish. The existing Mac-triggered Kubernetes test Jobs remain available while the GitHub Actions migration is tested.
