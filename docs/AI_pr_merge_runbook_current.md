# PR Merge Runbook (Current)

Generated: 2026-02-21 10:25 CET

## Scope

- Open PRs: 10
- Mergeable now: all 10
- Conflict pair: `#77` and `#40` both modify `kubernetes/apps/home-automation/n8n/app/helmrelease.yaml`

## Prerequisites

Run these once before merging any PR:

```bash
cd /home/mu/code/cberg-home-nextgen
gh auth status
gh pr list --state open --limit 100
git status --short
```

Use a clean tree for merge operations. If local docs are still modified, commit/stash them first or merge from another worktree.

Mandatory backup gate before any Kubernetes PR merge:

```bash
cd /home/mu/code/cberg-home-nextgen
KUBECONFIG=./kubeconfig kubectl get cronjobs -n storage | rg 'backup-of-all-volumes|daily-backup-all-volumes'
KUBECONFIG=./kubeconfig kubectl get jobs -n storage --sort-by=.status.startTime | tail -5
KUBECONFIG=./kubeconfig kubectl get volumes -n storage -o custom-columns=NAME:.metadata.name,LAST_BACKUP:.status.lastBackupAt,BACKUP:.status.lastBackup --no-headers
```

Backup gate pass criteria:

- Longhorn backup CronJob exists and is `Ready`
- Most recent backup job is `Completed`
- Volumes touched by the target app show a recent `LAST_BACKUP`

Hard stop conditions before each merge:

- PR mergeability is `CONFLICTING` (if `UNKNOWN`, run checks first and re-query)
- `gh pr checks <PR_NUMBER>` fails
- Changed files are outside expected scope for the PR

## Order

Recommended order:

1. Patch PRs: `#70`, `#72`, and (`#77` only if deferring n8n v2)
2. Minor PRs: `#71`, `#73`, `#74`, `#75`, `#76`
3. Major PRs: `#67`, `#40`

Decision gate before n8n:

- If short-term stability: merge `#77`, defer `#40`
- If direct major migration: skip/close `#77`, then merge `#40`

## Common Command Template

For each PR, run:

```bash
cd /home/mu/code/cberg-home-nextgen
# Backup gate first for any Kubernetes runtime PR
KUBECONFIG=./kubeconfig kubectl get cronjobs -n storage | rg 'backup-of-all-volumes|daily-backup-all-volumes'
KUBECONFIG=./kubeconfig kubectl get jobs -n storage --sort-by=.status.startTime | tail -5
gh pr view <PR_NUMBER> --json mergeable --jq .mergeable
gh pr checks <PR_NUMBER> --watch
gh pr view <PR_NUMBER> --json files --jq '.files[].path'
gh pr checkout <PR_NUMBER>
git switch main
gh pr merge <PR_NUMBER> --squash --delete-branch
```

Then verify Flux and workload health:

```bash
flux get kustomizations -A
KUBECONFIG=./kubeconfig kubectl get helmreleases -A
KUBECONFIG=./kubeconfig kubectl get pods -A
```

## PR-By-PR Commands And Validation

### PR #70 - Talos/Kubelet patch

- PR: `https://github.com/nachtschatt3n/cberg-home-nextgen/pull/70`
- File: `kubernetes/bootstrap/talos/talconfig.yaml`

Commands:

```bash
gh pr view 70 --json mergeable --jq .mergeable
gh pr checks 70 --watch
gh pr checkout 70
git switch main
gh pr merge 70 --squash --delete-branch
# This merge updates desired Talos/Kubernetes versions in git only.
# Apply your node upgrade workflow after merge, then validate:
KUBECONFIG=./kubeconfig kubectl get nodes -o custom-columns=NAME:.metadata.name,KUBELET:.status.nodeInfo.kubeletVersion,OS:.status.nodeInfo.osImage
```

Backup check:

- Confirm current Talos recovery media/config and etcd backup procedure are available before merge.
- Do not start node upgrades unless rollback boot assets are ready for each node.

Validation checklist:

- Node versions converge to desired Talos/Kubernetes versions
- All nodes return `Ready`
- No new warning events during rollout

Rollback plan:

- Revert PR merge commit in `main`, push, and reconcile Flux.
- Roll back nodes one-by-one to previous Talos/Kubernetes versions using your standard Talos upgrade rollback workflow.

### PR #72 - paperless-ngx patch

- PR: `https://github.com/nachtschatt3n/cberg-home-nextgen/pull/72`
- File: `kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml`

Commands:

```bash
gh pr view 72 --json mergeable --jq .mergeable
gh pr checks 72 --watch
gh pr checkout 72
git switch main
gh pr merge 72 --squash --delete-branch
KUBECONFIG=./kubeconfig kubectl -n office get pods | rg paperless-ngx
KUBECONFIG=./kubeconfig kubectl -n office logs deploy/paperless-ngx --tail=100 | rg -i "error|fail|exception"
```

Backup check:

- Confirm latest backup exists for Paperless PVC and backing DB/Redis volumes before merge.

Validation checklist:

- `paperless-ngx` pods restart and become `Running`
- Document ingest and UI login still work
- MariaDB/Redis sidecar pods remain healthy

Rollback plan:

- Revert PR merge commit in `main`, push, and reconcile Flux.
- If data inconsistencies appear, restore Paperless DB and PVC snapshots from the pre-merge backup point.

### PR #77 - n8n patch (optional path)

- PR: `https://github.com/nachtschatt3n/cberg-home-nextgen/pull/77`
- File: `kubernetes/apps/home-automation/n8n/app/helmrelease.yaml`

Commands:

```bash
gh pr view 77 --json mergeable --jq .mergeable
gh pr checks 77 --watch
gh pr checkout 77
git switch main
gh pr merge 77 --squash --delete-branch
KUBECONFIG=./kubeconfig kubectl -n home-automation get pods | rg n8n
KUBECONFIG=./kubeconfig kubectl -n home-automation logs deploy/n8n --tail=100 | rg -i "error|fail|exception"
```

Backup check:

- Verify current n8n DB backup and PVC snapshot exist before merge.

Validation checklist:

- n8n pod on `1.123.21`
- Queue/webhook/editor functions still execute
- No credential decryption errors

Rollback plan:

- Revert PR merge commit in `main`, push, and reconcile Flux.
- Restore n8n DB/PVC snapshot if workflow state is corrupted.

### PR #71 - postgres minor for Authentik cleanup job

- PR: `https://github.com/nachtschatt3n/cberg-home-nextgen/pull/71`
- File: `kubernetes/apps/kube-system/authentik/app/cronjob-channels-cleanup.yaml`

Commands:

```bash
gh pr view 71 --json mergeable --jq .mergeable
gh pr checks 71 --watch
gh pr checkout 71
git switch main
gh pr merge 71 --squash --delete-branch
KUBECONFIG=./kubeconfig kubectl -n kube-system get cronjob authentik-channels-cleanup -o yaml | rg "postgres:17.8"
KUBECONFIG=./kubeconfig kubectl -n kube-system get jobs --sort-by=.status.startTime | tail -5
```

Backup check:

- No application data migration expected, but confirm at least one recent cluster backup exists.

Validation checklist:

- CronJob spec updated to `postgres:17.8-bookworm`
- Next scheduled/triggered run completes successfully

Rollback plan:

- Revert PR merge commit in `main`, push, and reconcile Flux.
- If cleanup job starts failing, pin image back to `postgres:17.7-bookworm`.

### PR #73 - uptime-kuma chart minor

- PR: `https://github.com/nachtschatt3n/cberg-home-nextgen/pull/73`
- File: `kubernetes/apps/monitoring/uptime-kuma/app/helmrelease.yaml`

Commands:

```bash
gh pr view 73 --json mergeable --jq .mergeable
gh pr checks 73 --watch
gh pr checkout 73
git switch main
gh pr merge 73 --squash --delete-branch
KUBECONFIG=./kubeconfig kubectl -n monitoring get pods | rg uptime-kuma
KUBECONFIG=./kubeconfig kubectl -n monitoring logs deploy/uptime-kuma --tail=100 | rg -i "error|fail|exception"
```

Backup check:

- Confirm backup/snapshot exists for Uptime Kuma persistence volume.

Validation checklist:

- HelmRelease reconciles without values-schema errors
- Uptime Kuma monitors and notifications remain intact

Rollback plan:

- Revert PR merge commit in `main`, push, and reconcile Flux.
- Restore Uptime Kuma volume snapshot if monitor data is damaged.

### PR #74 - esphome minor

- PR: `https://github.com/nachtschatt3n/cberg-home-nextgen/pull/74`
- File: `kubernetes/apps/home-automation/esphome/app/helmrelease.yaml`

Commands:

```bash
gh pr view 74 --json mergeable --jq .mergeable
gh pr checks 74 --watch
gh pr checkout 74
git switch main
gh pr merge 74 --squash --delete-branch
KUBECONFIG=./kubeconfig kubectl -n home-automation get pods | rg esphome
KUBECONFIG=./kubeconfig kubectl -n home-automation logs deploy/esphome --tail=100 | rg -i "error|fail|exception"
```

Backup check:

- Confirm backup/snapshot of ESPHome config volume exists.

Validation checklist:

- ESPHome pod rolls to new tag
- Device compile/upload path still works
- Home Assistant integration remains connected

Rollback plan:

- Revert PR merge commit in `main`, push, and reconcile Flux.
- Restore ESPHome config snapshot if device configs are affected.

### PR #75 - jdownloader minor

- PR: `https://github.com/nachtschatt3n/cberg-home-nextgen/pull/75`
- File: `kubernetes/apps/download/jdownloader/app/helmrelease.yaml`

Commands:

```bash
gh pr view 75 --json mergeable --jq .mergeable
gh pr checks 75 --watch
gh pr checkout 75
git switch main
gh pr merge 75 --squash --delete-branch
KUBECONFIG=./kubeconfig kubectl -n download get pods | rg jdownloader
KUBECONFIG=./kubeconfig kubectl -n download logs deploy/jdownloader --tail=100 | rg -i "error|fail|exception"
```

Backup check:

- Confirm backup/snapshot of JDownloader config/download state volume exists.

Validation checklist:

- Pod runs on `v26.02.2`
- UI and download queue operate normally

Rollback plan:

- Revert PR merge commit in `main`, push, and reconcile Flux.
- Restore JDownloader state snapshot if queue state or config regresses.

### PR #76 - sops toolchain minor

- PR: `https://github.com/nachtschatt3n/cberg-home-nextgen/pull/76`
- File: `.mise.toml`

Commands:

```bash
gh pr view 76 --json mergeable --jq .mergeable
gh pr checks 76 --watch
gh pr checkout 76
mise install
sops --version
git switch main
gh pr merge 76 --squash --delete-branch
```

Backup check:

- Runtime data backup not required (tooling-only PR). Ensure local branch/worktree state is clean.

Validation checklist:

- `sops` resolves to expected version from mise
- Existing SOPS workflows (`sops -d`, `sops -e -i`) still function

Rollback plan:

- Revert PR merge commit in `main`, push.
- Re-run `mise install` to re-pin tool versions.

### PR #67 - kube-prometheus-stack major

- PR: `https://github.com/nachtschatt3n/cberg-home-nextgen/pull/67`
- File: `kubernetes/apps/monitoring/kube-prometheus-stack/app/helmrelease.yaml`

Commands:

```bash
gh pr view 67 --json mergeable --jq .mergeable
gh pr checks 67 --watch
gh pr checkout 67
git switch main
gh pr merge 67 --squash --delete-branch
KUBECONFIG=./kubeconfig kubectl -n monitoring get pods | rg "prometheus|alertmanager|kube-prometheus-stack"
KUBECONFIG=./kubeconfig kubectl -n monitoring get servicemonitors,prometheusrules
```

Backup check:

- Confirm backups/snapshots exist for monitoring PVCs (Prometheus/Alertmanager/Grafana if persistent).

Validation checklist:

- Operator, Prometheus, Alertmanager all reconcile cleanly
- Target scrape counts and alert flow remain stable
- No dashboard datasource breakage

Rollback plan:

- Revert PR merge commit in `main`, push, and reconcile Flux.
- If CRD/schema drift causes runtime failure, restore monitoring state volumes and re-apply previous chart version immediately.

### PR #40 - n8n major

- PR: `https://github.com/nachtschatt3n/cberg-home-nextgen/pull/40`
- File: `kubernetes/apps/home-automation/n8n/app/helmrelease.yaml`

Pre-merge backup gate:

```bash
# Take DB backup/snapshot before merging
# (run your existing backup workflow for n8n DB + PVC)
```

Commands:

```bash
gh pr view 40 --json mergeable --jq .mergeable
gh pr checks 40 --watch
gh pr checkout 40
git switch main
gh pr merge 40 --squash --delete-branch
KUBECONFIG=./kubeconfig kubectl -n home-automation get pods | rg n8n
KUBECONFIG=./kubeconfig kubectl -n home-automation logs deploy/n8n --tail=200 | rg -i "error|fail|exception|migration"
```

Validation checklist:

- Pod starts successfully on `2.9.1`
- Workflow executions and triggers still run
- Webhooks and credentials work post-migration
- Queue mode and Redis connectivity stable

Rollback gate:

- Revert PR and restore DB/PVC snapshot if workflow or credential compatibility fails.
- Rollback command path:
  - `MERGE_SHA=$(gh pr view 40 --json mergeCommit --jq '.mergeCommit.oid')`
  - `git switch main && git pull`
  - `git revert --no-edit "$MERGE_SHA"`
  - `git push`

## Post-Merge Global Verification

After each merged PR (or after each batch), run:

```bash
cd /home/mu/code/cberg-home-nextgen
flux get kustomizations -A
KUBECONFIG=./kubeconfig kubectl get helmreleases -A
KUBECONFIG=./kubeconfig kubectl get events -A --field-selector type=Warning --sort-by='.lastTimestamp' | tail -30
```

Standard rollback command path (all PRs):

```bash
MERGE_SHA=$(gh pr view <PR_NUMBER> --json mergeCommit --jq '.mergeCommit.oid')
git switch main
git pull
git revert --no-edit "$MERGE_SHA"
git push
```

After rollback, verify:

```bash
flux get kustomizations -A
KUBECONFIG=./kubeconfig kubectl get helmreleases -A
KUBECONFIG=./kubeconfig kubectl get pods -A
```

## Notes

- Scanner parsing issue is resolved: `tools/check-all-versions.py` now reports `Parsed 70 HelmReleases`.
- Renovate dashboard issue is still open: `https://github.com/nachtschatt3n/cberg-home-nextgen/issues/7`
