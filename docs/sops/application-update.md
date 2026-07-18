# SOP: Application Version Update / Upgrade

> Version: `2026.07.18`
> Last Updated: `2026-07-18`

## 1) Description

Default process for bumping an application's chart or image version in this
GitOps repo. Complements `new-deployment-blueprint.md` (that is for *new* apps;
this is for *updating* an existing one). Codifies the hard lessons from the
2026-07-18 superset and openclaw upgrades: **silence the app's alerts before a
disruptive update, drive the rollout so Flux's auto-rollback can't thrash it, and
keep a one-command revert path.**

## 2) Overview

Applies to any Flux HelmRelease (chart bump) or app-template image-tag bump. Three
risk tiers:
- **Low (patch, self-contained image):** commit + push, let Flux reconcile, verify.
- **Minor:** verify the target tag/chart exists in the registry FIRST, then as
  low, watching the rollout.
- **Attended (major / multi-minor chart / startup-migration apps / plugin hosts
  like openclaw):** silence alerts, disable rollback for the attempt, watch the
  init/migration, verify, restore rollback — or revert.

Key facts that bite:
- **Immutable Deployment selectors** (e.g. superset) fail `helm upgrade` across a
  relabel — you must delete the Deployments so Helm recreates them.
- **`Recreate` strategy + Flux `upgrade.remediation` rollback** = a crash-looping
  new pod gets rolled back before its init can run. Disable rollback for the run.
- **`maxHistory: 1`** means `helm rollback` can't reach the pre-upgrade revision.

## 3) Blueprints

N/A. Uses the app's existing HelmRelease + the Alertmanager silence API.

## 4) Operational Instructions

**Step 0 — verify the target exists** (never bump a version that isn't published):
```bash
# image tag: docker hub / ghcr
curl -s "https://hub.docker.com/v2/repositories/<repo>/tags/<tag>" -o /dev/null -w '%{http_code}\n'
# helm chart (OCI): ghcr token + manifest HEAD; or check the HelmRepository index.yaml
```

**Step 1 — silence the app's alerts (DEFAULT for attended updates).** Suppresses
the expected crash-loop/restart/not-ready noise so it doesn't page while you work:
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 &
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
  "matchers":[{"name":"namespace","value":"<ns>","isRegex":false,"isEqual":true},
              {"name":"alertname","value":"<App>.*|Kube(Pod|Deployment).*","isRegex":true,"isEqual":true}],
  "startsAt":"'$NOW'","endsAt":"'$END'","createdBy":"operator",
  "comment":"<app> vX->Y upgrade — suppressing rollout noise. auto-expires 4h"}'
```
Prefer a short TTL (4h) so it self-clears. Delete early once healthy:
`curl -s -X DELETE localhost:9093/api/v2/silences/<id>`.

**Step 2 — disable rollback for an attended/migration-risk update** (so the fixed
spec sticks and any init migration runs). Edit the HelmRelease:
```yaml
  upgrade:
    remediation:
      retries: 0
      remediateLastFailure: false   # restore retries:3 after success
```

**Step 3 — commit + push** the version bump (and any fix). Flux reconciles.

**Step 4 — watch the rollout** (see §6). For immutable-selector charts, delete the
Deployments once so Helm recreates them; do NOT hand-delete pods mid-`Recreate`.

**Step 5 — on success:** restore `retries: 3`, drop the silence, commit.
**On failure:** revert (see §11).

## 5) Examples

### Example A: low-risk image patch
Edit tag in the app's `helmrelease.yaml`, `git commit && git push`, then verify
(§6). No silence needed.

### Example B: attended chart major (superset 0.17.2 → 0.20.0)
Silence → bump → push → `helm upgrade` fails on immutable selector →
`kubectl delete deploy -n databases superset superset-worker superset-celerybeat`
→ `flux reconcile hr -n databases superset --force` → verify → drop silence.

## 6) Verification Tests

```bash
# HelmRelease reconciled to the new version, healthy
kubectl get helmrelease -n <ns> <app> -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'
# pods rolled, stable (0 restarts after settle), Ready
kubectl get pods -n <ns> -l app.kubernetes.io/name=<app>
# app health endpoint / running version
kubectl exec -n <ns> <pod> -c <c> -- <app-version-cmd>
```

## 7) Troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| `spec.selector: field is immutable` | chart relabelled Deployment selectors | delete the Deployments, `reconcile --force` |
| new pod crash-loops then reverts to old version | Flux `remediation` rollback | disable rollback (Step 2), retry |
| helm stuck `pending-upgrade` | crash-loop during `--wait`, or hand-deleting pods mid-Recreate | `helm rollback <app> <last-deployed> -n <ns> --wait=false`, then reconcile |
| `helm rollback` can't reach old version | `maxHistory: 1` pruned it | revert git spec instead (§11) |

## 8) Diagnose Examples

```bash
helm history <app> -n <ns>                 # revisions + which is deployed/pending
kubectl get helmrelease -n <ns> <app> -o jsonpath='{.status.conditions[?(@.type=="Released")].message}'
kubectl logs -n <ns> <pod> --previous --tail=40   # crash reason from the prior container
```

## 9) Health Check

Post-update: pod Ready + 0 restarts after settle; app health endpoint OK; the
silence expired or deleted; `flux get hr -A | grep <app>` READY=True; git ==
cluster version.

## 10) Security Check

- Never put a plaintext secret in values to satisfy an upgrade — wire via the
  app's SOPS secret / `existingSecret` (e.g. superset Redis `auth.existingSecret`).
- Silences are scoped + short-TTL; don't leave a broad silence open.
- Verify the new image/chart provenance (registry, digest) before bumping.

## 11) Rollback Plan

```bash
# Restore the exact known-good manifest, commit, reconcile:
git checkout <known-good-commit> -- kubernetes/apps/<path>/helmrelease.yaml
git commit -m "revert(<app>): back to <old-version>" && git push
# If helm is wedged pending-upgrade, clear it first:
helm rollback <app> <last-deployed-rev> -n <ns> --wait=false
flux reconcile helmrelease -n <ns> <app> --force
```

## 12) References

- `docs/sops/new-deployment-blueprint.md` (new apps)
- Live case studies: `docs/troubleshooting/openclaw-2026.7.1-upgrade.md`;
  memory `project_superset_chart_020_redis_auth`, `project_openclaw_2026_7_1_upgrade`

## Version History

| Version | Date | Change |
|---|---|---|
| 2026.07.18 | 2026-07-18 | Initial — codifies the superset/openclaw upgrade lessons (silence, disable-rollback, immutable-selector, pending-upgrade recovery, revert). |
