---
plan_id: affine-0.27.3
component: affine
pr: null                            # no open Renovate PR (held before/without a PR); bump the image tag by hand
kind: image
current: "0.27.1"
target: "0.27.3"
update_type: patch
risk: medium
est_duration_min: 20
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/affine
    - deployment/affine
    - pvc/affine-storage          # blobs/avatars/copilot data (longhorn, 20Gi)
    - pvc/affine-config           # /root/.affine/config (longhorn, 1Gi)
    - pvc/affine-pg-data          # postgres data (longhorn-static, Retain, 20Gi) — read by predeploy migration, not deleted
  shared: []                       # no shared infra perturbed: ingress class "internal" unchanged, no cert-manager/cni/coredns/shared-DB touch
depends_on: []
conflicts_with: []
status: awaiting-go                  # 2026-08-04 tue-early (unattended cron): risk
                                    # medium + auto_execute:false → fails the
                                    # unattended bar (max_unattended_risk: low).
                                    # go/no-go pushed to operator (openclaw
                                    # home-operation + urgent Telegram). NOT applied.
window: "tue-early:2026-08-04"
auto_execute: false
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
generated: "2026-07-31"
---

# affine 0.27.1 → 0.27.3

## 1) Summary & why held

Patch bump of the AFFiNE self-host image `ghcr.io/toeverything/affine`
`0.27.1 → 0.27.3` (namespace `office`). Bug-fix-only release train
(0.27.2: "Fix login status may be lost", "Fix MCP requests accidentally
intercepted"; 0.27.3: share-page/kanban fixes, Obsidian importer, GC of
outdated documents). No chart change — this plan does **not** touch the
`app-template` 3.7.3→5.0.0 chart bump (separately deny-listed).

**Why the auto-updater held it (two reasons, one of them a false positive):**

1. **Deny-list (`runbooks/auto-update-policy.yaml`)** — `*affine*` is blocked
   regardless of semver because "affine chart/image bumps carry breaking
   env→config.json changes even on patch tags." Belt-and-suspenders operator rule.
2. **G3 breaking-change gate** trips on the "Breaking change" banner in the
   0.27.3 notes:
   > Starting from server version 0.27, environment variables are no longer the
   > server's preferred source for reading configuration, and some environment
   > variables are no longer available. Please refer to
   > https://docs.affine.pro/self-host-affine/install/configuration to migrate
   > the configuration to `config.json`.

**Investigation result — the config-migration reason is a FALSE POSITIVE here.**
That banner describes the **0.27.0** event and AFFiNE re-appends the *identical*
text verbatim to every 0.27.x patch release (confirmed: 0.27.2 and 0.27.3 notes
carry the same wording, and neither introduces any *new* env-var removal). This
deployment is **already on 0.27.1 (post-migration)** and **already ships a
`config.json`** — mounted from ConfigMap `affine-configmap` at
`/root/.affine/config/config.json` (storages/blob/avatar/copilot/caldav/indexer).
The env vars still set in the HelmRelease
(`AFFINE_SERVER_EXTERNAL_URL`, `AFFINE_SERVER_HOST`, `AFFINE_SERVER_HTTPS`,
`AFFINE_INDEXER_ENABLED`, `DATABASE_URL`, `REDIS_SERVER_HOST/PORT`) are the
connection/bootstrap vars that remain valid in 0.27.x — the running 0.27.1 pod
(up 14d, Ready) proves they work. **No config.json edit and no env migration is
required for this bump.**

**Residual REAL risk (why risk: medium, not low).** The `predeploy` initContainer
runs `node ./scripts/self-host-predeploy.js` — a **Postgres schema migration** —
on every rollout, and the controller uses `strategy: Recreate` with Flux
`upgrade.remediation.retries: 3`. That is exactly the thrash trap in
`docs/sops/application-update.md` §2: a slow/failed migration on the new pod can
be auto-rolled-back before it finishes, flapping the release. Plus it's a
household-facing stateful app. So: treat as an **attended** update — disable Flux
rollback for the run, watch the migration, keep a one-command revert.

## 2) Pre-checks

```bash
# a) affine + its deps healthy and Ready before we start
kubectl get pods -n office -l app.kubernetes.io/name=affine
flux get hr -n office | grep -E 'affine|affine-pg|affine-redis'   # all Ready=True

# b) confirm current tag is 0.27.1 in BOTH places (predeploy + main)
grep -n 'toeverything/affine' -A2 kubernetes/apps/office/affine/app/helmrelease.yaml

# c) backups fresh for all three affine volumes (see docs/sops/backup.md)
for pv in \
  $(kubectl get pvc -n office affine-config  -o jsonpath='{.spec.volumeName}') \
  $(kubectl get pvc -n office affine-pg-data  -o jsonpath='{.spec.volumeName}') \
  $(kubectl get pvc -n office affine-storage -o jsonpath='{.spec.volumeName}'); do
  kubectl get volume -n storage $pv \
    -o custom-columns=NAME:.metadata.name,ROBUST:.status.robustness,LASTBACKUP:.status.lastBackupAt --no-headers
done
# Expect robustness=healthy and a lastBackupAt within the last ~24h. If pg-data
# has no recent backup, take one before proceeding (backup SOP) — it holds all docs.

# d) verify the target image tag exists (no-v form!) — must be HTTP 200
TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:toeverything/affine:pull" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s -o /dev/null -w '0.27.3 -> %{http_code}\n' -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json" \
  https://ghcr.io/v2/toeverything/affine/manifests/0.27.3

# e) no in-flight reconcile
flux get kustomizations -A | awk 'NR==1 || $5!="True"'
```

## 3) Steps (GitOps, copy-pasteable)

> The image tag is pinned in **TWO** places in the HelmRelease — the `predeploy`
> initContainer **and** the `main` container. Both must move to `0.27.3` or the
> migration runs on a different version than the server. Use the bare tag
> `0.27.3` (NOT `v0.27.3` — the ghcr image tag has no `v`; the `v` form 404s).

1. **Silence + active-update marker** (per application-update SOP §1). Suppresses
   the expected `Recreate` restart / not-ready noise while the predeploy migration runs:
   ```bash
   runbooks/update-marker.sh add affine office 1 "0.27.1->0.27.3 patch"
   # optional Alertmanager silence (ns=office, ~1h TTL) per SOP §1 if it tends to page
   ```

2. **Disable Flux rollback for the run** so a slow predeploy migration isn't
   auto-remediated mid-flight. Edit `kubernetes/apps/office/affine/app/helmrelease.yaml`:
   ```yaml
     upgrade:
       timeout: 20m
       cleanupOnFail: true
       remediation:
         retries: 0                 # was 3 — RESTORE to 3 after success (step 6)
   ```

3. **Bump both image tags** in `kubernetes/apps/office/affine/app/helmrelease.yaml`:
   - `controllers.main.initContainers.predeploy.image.tag: 0.27.1` → `0.27.3`
   - `controllers.main.containers.main.image.tag: 0.27.1` → `0.27.3`

   ```bash
   sed -i '' 's/tag: 0\.27\.1/tag: 0.27.3/g' kubernetes/apps/office/affine/app/helmrelease.yaml
   grep -n 'toeverything/affine' -A2 kubernetes/apps/office/affine/app/helmrelease.yaml   # confirm BOTH now 0.27.3
   ```
   (The `sed` is safe: `0.27.1` appears only on the two affine image tags in this file.)

4. **No config.json / env change.** Leave `configmap.yaml` and all `env:` blocks
   as-is (see Summary — migration already done at 0.27.0). Do not touch
   `affine-pg` or `affine-redis`.

5. **Commit + push** (work on `main`, stage only these hunks):
   ```bash
   git add -p kubernetes/apps/office/affine/app/helmrelease.yaml
   git commit -m "feat(affine): update image ( 0.27.1 → 0.27.3 )"
   git push
   ```
   Flux webhook reconciles. `Recreate` terminates the old pod, then the new pod
   runs wait-for-postgres → wait-for-redis → **predeploy (DB migration)** → main.

6. **On success**, restore rollback and clear the marker/silence:
   ```bash
   # edit helmrelease.yaml: upgrade.remediation.retries back to 3
   git add -p kubernetes/apps/office/affine/app/helmrelease.yaml
   git commit -m "chore(affine): restore upgrade rollback retries after 0.27.3" && git push
   runbooks/update-marker.sh clear affine
   # delete the Alertmanager silence if one was created
   ```

## 4) Verification

```bash
# HelmRelease reconciled + Ready, pod rolled and stable (0 restarts after settle)
kubectl get hr -n office affine -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
kubectl get pods -n office -l app.kubernetes.io/name=affine

# predeploy migration ran clean (this is the load-bearing check for a patch bump)
POD=$(kubectl get pod -n office -l app.kubernetes.io/name=affine -o jsonpath='{.items[0].metadata.name}')
kubectl logs -n office $POD -c predeploy | tail -30        # no migration errors
kubectl get pod -n office $POD -o jsonpath='{.spec.containers[?(@.name=="main")].image}{"\n"}'   # -> ...affine:0.27.3

# server up on 3010 (tcpSocket probe already gates readiness) + HTTP reachable in-cluster
kubectl -n office exec deploy/affine -c main -- sh -c 'wget -qO- --timeout=5 http://localhost:3010/ >/dev/null && echo OK' 2>/dev/null || \
  kubectl -n office run affine-check --rm -it --restart=Never --image=busybox -- wget -qS -O/dev/null http://affine.office.svc.cluster.local:3010/ 2>&1 | tail -3

# data intact: open https://affine.<DOMAIN>, load a known workspace/doc, confirm
# blobs render and CalDAV/Nextcloud calendar still lists. Desktop/mobile clients
# (0.26+) still sync — 0.27 server accepts them per the compat note.
```

Success = HR Ready=True, one affine pod Ready with 0 restarts after ~3 min,
predeploy log clean, image is `...affine:0.27.3`, and an existing doc opens with
its blobs.

## 5) Rollback

Patch downgrade is safe here (no destructive schema change in the 0.27.x patch
line; `affine-pg-data` is `Retain` + longhorn-static). Revert the tag bump:

```bash
# fastest: revert the bump commit (restores BOTH tags + rollback setting)
git revert --no-edit <bump-commit-sha>
git push
flux reconcile helmrelease -n office affine --force

# if helm wedged in pending-upgrade (crash-loop during --wait):
helm history affine -n office                       # find last deployed rev
helm rollback affine <last-deployed-rev> -n office --wait=false
flux reconcile helmrelease -n office affine --force
```

Confirm back-to-good:
```bash
kubectl get pod -n office -l app.kubernetes.io/name=affine \
  -o jsonpath='{.items[0].spec.containers[?(@.name=="main")].image}{"\n"}'   # -> ...:0.27.1
kubectl get hr -n office affine -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'  # True
```
Then clear the marker/silence. If a DB restore is ever needed, restore
`affine-pg-data` from the Longhorn backup captured in Pre-check (c) per
`docs/sops/backup.md`.

## 6) Interference notes

- **Blast radius is one namespace, one pod.** Only the `affine` main deployment
  restarts (brief downtime under `Recreate` while the new pod runs the predeploy
  migration — expect ~1–3 min unavailable). `affine-pg` and `affine-redis` are
  **not** modified and stay up.
- **`shared: []` — nothing shared is perturbed.** Ingress class `internal` and the
  Homepage annotations are untouched (no ingress-controller restart). Copilot is
  wired to the external Ollama host (192.168.30.111) read-only — no cluster infra
  touched. Safe to co-schedule with any other plan; no `conflicts_with`.
- **Two-tag gotcha** (predeploy + main) — the single biggest execution error would
  be bumping only one. Both must read `0.27.3`.
- **Thrash trap** — `Recreate` + Flux `remediation.retries:3` can auto-roll-back a
  slow migration. Step 2 sets `retries:0` for the run; **remember to restore 3**
  (step 6). If skipped and the migration is slow, the release will flap.
- **Not a reboot job** (`needs_reboot: false`) and low-blast — fits a short
  no-reboot tue/thu window. Operator-present preferred only because of the on-start
  DB migration, not because of scope.
