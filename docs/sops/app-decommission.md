# SOP: Application Decommission

> Description: How to remove an application from the cluster for good — workloads, storage, databases, SSO objects, alerts, image automation, sweep policy rows, maintenance plans, source-repo automation and documentation — without losing data that was meant to be kept and without leaving inert config behind.
> Version: `2026.10.04`
> Last Updated: `2026-10-04`
> Owner: `cberg-home-ops`

---

## 1) Description

A decommission is the reverse of `docs/sops/new-deployment-blueprint.md`, and
it is more dangerous than a deployment: almost every step deletes something.
This SOP captures the procedure used on 2026-10-04 to retire 16 apps in one
operator-approved batch (`ac7bf0e0`, `c3c92dcd`, `53a18b79`, `722a2773` and
follow-ups): hermes-agent, librechat, scrypted-nvr, actual-budget, omni-tools
and 11 showcase apps.

The ordering principle: **make every delete reversible before doing it, and
delete in the order where a mistake is caught by the next step.** Data is
backed up and verified first, PVs are flipped to `Retain` before Flux prunes
anything, the GitOps removal lands next, and only then are the retained
objects deleted by hand.

- Scope: any app under `kubernetes/apps/<namespace>/<app>/`, its Longhorn /
  CIFS storage, its MariaDB/Postgres database, its Authentik provider +
  application, its PrometheusRule, its image automation, its sweep-DB policy
  rows and findings, its maintenance plans, its home-operation issues, and its
  source repo's scheduled workflows.
- Prerequisites: explicit operator decision naming the apps (a relayed agent
  message is not consent); mise toolchain; SOPS age key; sweep DSN for
  `runbooks/policy-cli.py`; GitHub access to the source repos for self-built
  images.
- Out of scope: deleting data on the NAS shares themselves, and deleting
  container images from GHCR. Both stay unless the operator asks separately.

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Removal mechanism | Comment out the app's `ks.yaml` line in `kubernetes/apps/<ns>/kustomization.yaml`; Flux prune removes the workloads |
| App directory | **Kept** in the repo (commented-out entry) so a revert restores it; doc-check counts directories, so counts do not change |
| Storage rule | `docs/sops/storage-safety.md` — read before any PV/PVC delete; CIFS deletes are object-only |
| SSO source of truth | `kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml` (blueprint, 2-stage removal) |
| Alerts | `kubernetes/apps/monitoring/kube-prometheus-stack/app/{app}-alerts.yaml` (comment out in the kustomization) |
| Policy rows | sweep_history Postgres via `runbooks/policy-cli.py` (`risk`, `finding`) |
| Plans | `runbooks/maintenance/plans/*.md` (delete; fix `conflicts_with`/`depends_on` refs) |
| Code special-cases | `runbooks/auto-update-policy.yaml`, `runbooks/coverage.py` (`CHANNEL_RULES`), `runbooks/security-check.py` (allowlists) |

---

## 3) Blueprints

The Authentik part of a decommission is a blueprint change, never a UI delete.
Removal is **two commits**, because Authentik applies `state: absent` entries
in document order and a provider deleted before its application leaves the
application row orphaned (observed 2026-10-04 on librechat: the first attempt
flipped the existing entries to `absent` in place, provider first, with full
attrs — the blueprint reported "successful" but the application survived).

- Source of truth file: `kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml`
- Stage 1 — rewrite the app's key as **minimal, identifiers-only** absent
  entries, **application before provider** (this also removes the old client
  credentials from the blueprint text):

```yaml
# Stage 1 (inside the app's blueprint key; edit with sops, not by hand)
version: 1
metadata:
  name: <app>-decommission
entries:
  - model: authentik_core.application
    state: absent
    identifiers:
      slug: <app>
  - model: authentik_providers_oauth2.oauth2provider
    state: absent
    identifiers:
      name: <app>
```

- Stage 2 — after verifying both objects are gone (Test 3), delete the key.
- Use `EDITOR=<script> sops <file>` so only that key's ciphertext changes
  (see the sops-editor memory note); never decrypt to `/tmp` and re-encrypt.

---

## 4) Operational Instructions

### 4.1 Inventory (read-only)

1. For each app, list everything it owns:

```bash
NS=<ns>; APP=<app>
mise exec -- kubectl get deploy,sts,cronjob,job,svc,httproute,pvc -n $NS | grep -i $APP
mise exec -- kubectl get pv -o custom-columns=PV:.metadata.name,CLAIM:.spec.claimRef.name,NS:.spec.claimRef.namespace,SC:.spec.storageClassName,RECLAIM:.spec.persistentVolumeReclaimPolicy | grep -i $APP
mise exec -- kubectl get volume -n storage | grep -i $APP
rg -l -i "$APP" kubernetes/ runbooks/ docs/ .github/ | sort
```

2. Note shared resources the app only *uses* (MariaDB/Postgres databases,
   Redis DB index, Authentik provider, LB IP, i915 slot) — those are cleaned
   in later steps, not by the prune.

### 4.2 Storage pre-flight and backup verification

1. **Every PV the app owns must be `Retain` before the prune.** Dynamic
   `longhorn` PVs default to `Delete`; patch them (this is the one direct
   cluster mutation the procedure needs before the commit, and it is the
   one that makes the prune non-destructive):

```bash
mise exec -- kubectl patch pv <pv> -p '{"spec":{"persistentVolumeReclaimPolicy":"Retain"}}'
```

2. **Every Longhorn volume needs a Completed backup newer than 24 h** on the
   NAS target. `lastBackupAt` can lag one cycle — check the Backup CR:

```bash
mise exec -- kubectl get backups.longhorn.io -n storage -l backup-volume=<volume> \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,CREATED:.status.backupCreatedAt
```

3. **CIFS PVs**: run the 3-step pre-flight from `docs/sops/storage-safety.md`
   (`subdir`, `reclaimPolicy`, StorageClass). A root/empty `subdir` is a
   STOP regardless of reclaim policy. A CIFS PV/PVC delete must be
   **object-only** — the share contents stay on the NAS.

### 4.3 Database dump, then drop

For apps with a database on the shared MariaDB/Postgres:

1. Dump to the Mac (outside the repo), verify the dump is non-empty and
   restorable (`gzip -t`, a byte floor, `CREATE TABLE` count > 0).
2. Only then `DROP DATABASE` and `DROP USER` for that app.
3. Record the dump location in the decommission commit message (path only,
   no credentials). On 2026-10-04: `~/mariadb-dumps/decommission-20261004/`.

### 4.4 GitOps removal (one commit)

1. Comment out `- ./<app>/ks.yaml` in `kubernetes/apps/<ns>/kustomization.yaml`
   with a dated reason (`# DISABLED YYYY-MM-DD (operator: decommissioned …)`).
2. Same commit, the dependents that would otherwise break or alert:
   - the app's PrometheusRule entry in
     `kubernetes/apps/monitoring/kube-prometheus-stack/app/kustomization.yaml`
     (a rule left loaded fires `absent()` / PodNotReady forever);
   - ImageRepository / ImagePolicy for self-built images (leave the shared
     ImageUpdateAutomation if other apps still use it);
   - Flux sources used only by this app (HelmRepository / OCIRepository);
   - Authentik **stage 1** (§3);
   - `docs/applications.md` row marked `**DECOMMISSIONED YYYY-MM-DD**`,
     README note, freed LB IP in `docs/infrastructure.md`.
3. Validate, commit with `git commit --only <paths>`, push. Flux prunes.

```bash
mise exec -- task kubeconform
git commit --only <paths> -F <unique-msg-file>
git show --stat HEAD && git log -1 --format=%s
git pull --rebase --autostash && git push
```

### 4.5 Post-prune deletes (explicit, after verification)

1. Confirm workloads are gone (Test 1). Then delete the now-Released
   Retain PVs and their Longhorn volumes **one by one**, only for volumes
   with the verified backup from §4.2. CIFS: delete the PV object only.
2. Authentik **stage 2**: drop the blueprint key once Test 3 passes.

### 4.6 Sweep / policy / plan clean-up

1. **Maintenance plans** for the app: delete the plan file (plans are
   transient — `runbooks/maintenance/plans/README.md`); remove any
   `conflicts_with` / `depends_on` refs to it in other plans per the dead-ref
   convention; `python3 runbooks/maintenance-plan.py --validate` must report
   all invariants holding.
2. **home-operation go/no-go issues** for those plans: resolve with
   `home-operation resolve --issue <plan_id> --by superseded --note "<sha>"`
   — never `decide … approve`. Rebuild issues (`rebuild:<repo>`) for
   self-built images resolve the same way.
3. **Findings** owned by a plan or no automated closer:
   `runbooks/policy-cli.py finding close <F-id> --reason "app decommissioned YYYY-MM-DD" --commit <sha>`.
   Sweep-emitted image/version findings drop off on the next sweep once the
   workload is gone.
4. **Accepted risks** scoped to the app: `risk disable AR-0xx --reason "app decommissioned YYYY-MM-DD"`.
   For an AR covering several apps, edit the description — **preview with
   `risk match` first**; it is a substring needle, so confirm the match set
   before and after is the same minus the removed app. Register-only ARs
   (enforced in code) match nothing either way; edit them for accuracy.
5. **Code special-cases** naming the app: deny rules in
   `runbooks/auto-update-policy.yaml` (bump `version`), `CHANNEL_RULES` in
   `runbooks/coverage.py`, allowlists in `runbooks/security-check.py`. If a
   regression test was written against the app, keep the test and inject the
   app as a fixture — the guard tests the mechanism, not the app.

### 4.7 Source repos (self-built images)

Disable scheduled workflows in each app's source repo so a weekly rebuild
does not keep pushing images nobody runs:

```bash
gh workflow list -R <owner>/<repo>
gh workflow disable <workflow> -R <owner>/<repo>
```

Do not delete the repo or its GHCR packages unless the operator asks.

### 4.8 Documentation drift

Run `python3 runbooks/doc-check.py` and grep the repo for the app name.
**Remove** the app from live inventories and how-tos (consumer tables,
health-check loops, allowlists, counts). **Mark** it (`decommissioned
YYYY-MM-DD`) where the doc is a changelog or migration log. Agent
instruction files (`CLAUDE.md`/`AGENTS.md`, `.claude/agents/*.md`) change
only on the operator's own instruction.

---

## 5) Examples

### Example A: stateless app, no SSO (omni-tools)

Comment out the ks entry and the alert rule, close/disable its findings and
AR, update docs. No storage, no DB, no blueprint stage.

### Example B: stateful app with SSO (librechat)

Longhorn PVs patched to Retain + backup verified → GitOps removal with
Authentik stage 1 → stage 1 found the application surviving (provider-first
order) → rewrite to identifiers-only, application-first → verify both gone
→ stage 2 drops the key → delete Released PVs/volumes.

### Example C: CIFS-backed app (scrypted-nvr)

`cifs-scrypted-media` (subdir `/media`, Retain, app-dedicated class) passed
the pre-flight; PV deleted object-only after the prune. Its pre-release
channel hold (`*scrypted*` deny rule + `CHANNEL_RULES` entry), its
`ACCEPTED_PRIVILEGED` / `ACCEPTED_ROOT_UID` entries and its AR were retired
in follow-ups; the channel-rule tests kept scrypted as a fixture.

---

## 6) Verification Tests

### Test 1: workloads pruned

```bash
mise exec -- flux get kustomizations -A | grep -i <app>
mise exec -- kubectl get all,httproute -n <ns> | grep -i <app>
```

Expected:
- No Kustomization and no workload/route objects for the app.

If failed:
- `flux get kustomizations -A` for the parent namespace Kustomization; prune
  requires the parent to reconcile Ready.

### Test 2: storage gone (after §4.5), backups still present

```bash
mise exec -- kubectl get pv,volume -A 2>/dev/null | grep -i <app>
mise exec -- kubectl get backups.longhorn.io -n storage -l backup-volume=<volume>
```

Expected:
- No PV / Longhorn Volume; the Backup CRs from §4.2 still listed.

If failed:
- A PV stuck `Released` is waiting for the explicit delete in §4.5.

### Test 3: Authentik objects gone

```bash
mise exec -- kubectl -n kube-system exec deploy/authentik-server -- ak shell -c \
  "from authentik.core.models import Application; from authentik.providers.oauth2.models import OAuth2Provider; print(Application.objects.filter(slug='<app>').count(), OAuth2Provider.objects.filter(name='<app>').count())"
```

Expected:
- `0 0`, and the blueprint instance status is `successful`.

If failed:
- Application survived → stage 1 was not identifiers-only/application-first.

### Test 4: no dangling references

```bash
python3 runbooks/maintenance-plan.py --validate
python3 runbooks/doc-check.py
bash runbooks/tests/run-all.sh -q
```

Expected:
- Plan invariants hold, doc-check 0 critical, all test suites pass.

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| Authentik application still exists after stage 1 | provider deleted first / full attrs with a KeyOf to the deleted provider | rewrite as identifiers-only, application first (§3) |
| PrometheusRule alerts fire for the removed app | rule file still in the kube-prometheus-stack kustomization | comment it out (§4.4) |
| `maintenance-plan.py --validate` reports `DEAD-REF` | another plan's `conflicts_with`/`depends_on` names the deleted plan | remove the ref with a dated `# RESOLVED` comment |
| go/no-go reminder keeps firing for a deleted plan | home-operation issue still open | `home-operation resolve --issue <plan_id> --by superseded` |
| Weekly rebuild issue reappears | source repo scheduled workflow still enabled | `gh workflow disable` (§4.7) |
| PVC delete hangs | pod still mounting / finalizer | confirm Test 1 first; never force-remove finalizers on CIFS PVs |

---

## 8) Diagnose Examples

### Diagnose Example 1: is a PV safe to delete?

```bash
PV=<pv>
mise exec -- kubectl get pv $PV -o jsonpath='{.spec.persistentVolumeReclaimPolicy} {.spec.storageClassName} {.spec.csi.driver} {.spec.csi.volumeAttributes.subdir}{"\n"}'
```

Expected:
- Longhorn: a Completed Backup CR exists for its volume. CIFS: non-root
  `subdir`, and you are deleting the object only.

If unclear:
- Stop and ask; see `docs/sops/storage-safety.md`.

### Diagnose Example 2: what still references the app?

```bash
rg -n -i "<app>" docs/ runbooks/ .github/ kubernetes/ | grep -v -i decommission
mise exec -- python3 runbooks/policy-cli.py finding list --grep <app>
mise exec -- python3 runbooks/policy-cli.py risk list | grep -i <app>
```

Expected:
- Only intentionally kept history (changelogs, commented-out ks entries).

---

## 9) Health Check

```bash
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
mise exec -- kubectl get pv | grep -c Released
```

Expected:
- All Kustomizations Ready; no Released PVs left over from the decommission.

---

## 10) Security Check

```bash
git show --stat HEAD
mise exec -- kubectl get httproute -A | grep -i <app>
```

Expected:
- No plaintext secret or client credential in any commit (blueprint edits
  touch only that key's ciphertext).
- No route still publishes the app's hostname; Authentik provider gone, so
  no OIDC client remains for a dead app.
- No allowlist (`ACCEPTED_PRIVILEGED`, `ACCEPTED_ROOT_UID`, etc.) or AR still
  exempts a workload that no longer exists — an exemption left behind would
  silently cover a future workload reusing the name.

---

## 11) Rollback Plan

- **Before §4.5** (PVs still Retained): `git revert <decommission sha> && git push`.
  Flux re-creates the workloads; re-bind the Retain PVs (clear
  `spec.claimRef`) so the new PVCs attach the old data.
- **After §4.5**: restore each Longhorn volume from the Backup CR verified in
  §4.2 (`docs/sops/backup.md`), recreate the static PV/PVC, then revert.
  CIFS data was never deleted. Restore databases from the dumps (§4.3).
- Authentik: revert both stage commits; the blueprint re-creates provider +
  application (new client secret — update the app's SOPS secret).
- Source repos: `gh workflow enable <workflow> -R <owner>/<repo>`.

---

## 12) References

- `docs/sops/storage-safety.md`, `docs/sops/longhorn.md`, `docs/sops/backup.md`
- `docs/sops/authentik.md`
- `docs/sops/new-deployment-blueprint.md` (the inverse procedure)
- `docs/sops/maintenance-windows.md`, `runbooks/maintenance/plans/README.md`
- `docs/sops/policy-cli.md`, `docs/sops/self-built-image-rebuild.md`
- Commits: `ac7bf0e0`, `c3c92dcd`, `53a18b79`, `722a2773`

---

## Version History

- `2026.10.04`: Initial SOP, from the 2026-10-04 decommission of 16 apps.
