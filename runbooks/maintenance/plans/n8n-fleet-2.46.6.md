---
plan_id: n8n-fleet-2.46.6
component: n8n
pr: 476                               # Renovate "chore(deps): update n8nio/n8n docker tag to v2.46.6",
                                      # OPEN, MERGEABLE/CLEAN, CI green (Flate Render Gate, Flux Local Diff x2),
                                      # diff = exactly 1 line (tag "2.44.5" -> "2.46.6"), measured 2026-11-08.
kind: image
current: "2.44.5"                     # LIVE 2026-11-08: deploy/n8n image n8nio/n8n:2.44.5, pod imageID
                                      # sha256:bcb4e491..., `n8n --version` 2.44.5, node v26.10.0, chart 2.1.1.
                                      # The superseded n8n-fleet-2.44.6 NEVER executed, so the span is two minors.
target: "2.46.6"                      # newest STABLE at 2026-11-08: npm dist-tag `stable` = `latest` = 2.46.6, and
                                      # Docker Hub n8nio/n8n:2.46.6 == :stable == :latest ==
                                      # sha256:8602f5dfacbe2c931eeafd010de0e68182310e9f309921e780ab69182e92b3ae
                                      # (pushed 2026-11-04T13:05Z). GitHub n8n@2.46.4/.5/.6 are prerelease=false;
                                      # 2.46.0..2.46.3 and everything on `beta`/`next`/`rc` (2.47.2) are not stable.
update_type: minor
risk: medium                          # 23 NEW forward-only schema migrations on a 512 MB SQLite file, two minors,
                                      # restart blocks on migration time. Mitigations: scratch rehearsal of the exact
                                      # image digest on a restored copy BEFORE the live edit, Mac-side tar + Longhorn
                                      # backup, and an instance that currently has 0 published workflows (§1.4).
est_duration_min: 60                  # normal path: 15 backup+integrity + 20 scratch rehearsal + 5 edit/push + 8 migrate/Recreate + 12 verify.
                                      # Failure path ceiling is separate: <= 42 min upgrade deadline + ~15-20 min restore (inside 180).
                                      # + 12 verify. Fits the 70-minute attended-window budget (duration_min - 20).
needs_reboot: false
touches:
  namespaces: [home-automation, storage]   # storage: scratch Longhorn Volume + Backup CR read (rehearsal only)
  resources:
    - helmrelease/n8n                 # edited: values.image.tag + spec.timeout + values.main.startupProbe (one commit, §3.2)
    - deployment/n8n                  # pod-template change -> Recreate; down for the whole migration (§1.3)
    - service/n8n                     # unchanged; single endpoint absent during Recreate
    - pvc/n8n-config                  # RWO Longhorn, 5Gi; database.sqlite is MIGRATED FORWARD in place
    - volume.longhorn.io/n8n-config   # source of the Backup CR used by the rehearsal and by rollback path B
    - httproute/n8n                   # not edited; backend absent during Recreate (envoy-external)
    - scratch pod/pvc/pv/volume n8n-rp-*   # created and deleted inside §2.6, label restore-proof=true
  shared: [longhorn, envoy-external]  # longhorn: backup read + scratch volume; envoy-external: the public hostname
                                      # 5xx/404s for the Recreate. No shared DB: n8n is SQLite, not postgres.
depends_on: []                        # chart 2.1.1 is live (premise chart-2-1-1); no unmet predecessor.
conflicts_with:
  - longhorn-1.13.0                   # sun-attended:2026-11-15: engine/manager roll while this plan relies on a
                                      # restorable Backup CR and a scratch Longhorn volume. Never the same night.
  - talos-linux-1.14.5                # sun-attended:2026-11-22: node reboots; n8n-config is RWO and a Recreate
                                      # plus a node drain stacks two reasons for a failed boot.
  - flux-oci-chart-sources            # sun-attended:2026-12-13: rewrites hr/n8n's chart source (two writers).
  - helm-drift-detection              # sat-attended:2026-11-28: adds a spec field to every HelmRelease incl. n8n.
                                      # NOTE: none of these four plans names n8n-fleet-* in its own frontmatter
                                      # (reciprocity is not checked by --validate); declared here only.
exclusive: false
security_ref: F-d8bf68df              # open critical on the CURRENT tag 2.44.5 (detail lives on the finding
                                      # record, never here). Whether 2.46.6 clears it is NOT claimed measured:
                                      # §4 V10 re-reads it after execution.
capability_change: true               # FACT, not caution: 2.45/2.46 add new agent/skills-hub/self-healing tables
                                      # and APIs, "Authenticate Webhook and MCP Trigger nodes through trusted
                                      # sources" (new auth modes on those nodes), granular credential sharing
                                      # always-on (#41376), and a v3 migration-report surface. None is enabled by
                                      # an env change here, but the software can do more than 2.44.5.
rollback_class: backup-restore        # NOT git-revert: 23 migrations are forward-only (§1.3). A tag revert alone
                                      # puts 2.44.5 against a migrated DB. Restore is a procedure (§5).
backup_gate: "§2.5 passes in full: (a) newest Completed Longhorn Backup CR for volume n8n-config is < 26 h old; (b) a Mac-side tar of database.sqlite + -wal + -shm + config streamed from the live pod, size >= 500000000 bytes, that on extraction passes sqlite3 PRAGMA integrity_check == ok, workflow_entity count == 15 and migrations count == 302 with newest AddTimeoutSecondsToScheduler1791542683581; (c) §2.6 scratch rehearsal of image 2.46.6@sha256:8602f5df... on a restore of (a) reaches readiness 200 inside 300 s, ends with newest migration AddSkillMcpAvailability1793000146414, workflow count 15 and the smoke execution marker. All three before the tag edit is pushed."
finding_refs:                         # queried 2026-11-08 (`policy-cli.py finding list --grep n8n`)
  - F-09588936                        # "n8n: image n8nio/n8n 2.44.5 -> 2.46.6 (minor)" - the version finding
  - F-d8bf68df                        # critical on n8nio/n8n:2.44.5 "newer upstream tag available, bump the
                                      # image" - the bump IS the household's only remedy for a third-party image.
                                      # Close against the §3.3 commit only after V10 re-measures it.
restore_proof: "§2.6: the newest Completed Longhorn Backup CR of n8n-config is restored into a SCRATCH Longhorn volume (n8n-rp-*, label restore-proof=true), the exact target image 2.46.6@sha256:8602f5df... is booted on it with the live resources, and BEFORE the tag edit is pushed it must reach /healthz/readiness 200, report node v26.12.1 and n8n 2.46.6, list 15 workflows with active cksum 3124227881 136, process 0 published workflows, and execute an imported smoke workflow (marker rp-smoke-ok absent in the pre-import control, present after). The scratch objects are then deleted and the count of restore-proof volumes must read 0."
supersedes: n8n-fleet-2.44.6
review: ready-for-go@2026-11-08   # plan-reviewer 2026-11-08: needs-fix x3 (Helm timeout/startupProbe, rehearsal realism, rollback vs Helm remediation race, R1b empty-read/UpgradeFailed gaps), fixed (remediation retries 0 for the window, hardened R1b), final blocking-only review ready-for-go; HUMAN-GATED, GO at the window
status: vetted
window: "sun-attended:2026-12-06"   # coordinator choice after review (60 of 180 schedulable min); 2nd choice sun-attended:2026-11-29
premises:
  - id: chart-2-1-1
    why: "Live-state guard: the plan assumes chart 2.1.1 is what renders the Deployment (Recreate strategy, enableServiceLinks)."
    run: kubectl get helmrelease -n home-automation n8n -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "2.1.1"
  - id: image-is-2-44-5
    why: "The whole analysis is 2.44.5 -> 2.46.6. If Step 0 or the operator already merged PR 476 or the old patch plan ran, re-plan."
    run: kubectl get deploy -n home-automation n8n -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: n8nio/n8n:2.44.5
  - id: git-tag-pin-2-44-5
    why: "Git side of the same premise; the section 3.2 sed must hit exactly one line."
    run: "git show HEAD:kubernetes/apps/home-automation/n8n/app/helmrelease.yaml | grep -c 'tag: \"2.44.5\"'"
    expect_exact: "1"
  - id: helmrelease-ready
    why: "Do not stack an image bump on a release left Failed."
    run: kubectl get helmrelease -n home-automation n8n -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: strategy-recreate
    why: "Single replica on RWO Longhorn PVC: RollingUpdate risks Multi-Attach on the pod-template change (docs/sops/longhorn-rwo-multi-attach.md)."
    run: kubectl get deploy -n home-automation n8n -o jsonpath='{.spec.strategy.type}'
    expect_exact: Recreate
  - id: single-replica-main-only
    why: "The 'fleet' is ONE deployment. If a worker/webhook/valkey deployment appears (queue mode), this plan's SQLite assumptions are void."
    run: kubectl get deploy -n home-automation -o name | grep -c n8n
    expect_exact: "1"
  - id: sqlite-not-postgres
    why: "No DB_TYPE env => embedded SQLite on the PVC. A DB_TYPE=postgresdb would make the backup and rollback sections wrong and add the postgres plans to conflicts_with."
    run: kubectl get deploy -n home-automation n8n -o yaml | grep -c DB_TYPE
    expect_exact: "0"
  - id: pvc-bound
    why: "Rollback path A and the rehearsal both depend on this exact PVC/volume name."
    run: kubectl get pvc -n home-automation n8n-config -o jsonpath='{.status.phase}'
    expect_exact: Bound
  - id: longhorn-volume-healthy
    why: "A degraded volume cannot be trusted as the source of backup B1."
    run: kubectl get volumes.longhorn.io -n storage n8n-config -o jsonpath='{.status.robustness}'
    expect_exact: healthy
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/longhorn.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/auto-update.md
generated: "2026-11-08"
---

# n8n: image 2.44.5 -> 2.46.6 (newest stable; retargeted from 2.44.6)

## 1) Summary & why held

### 1.1 What changes

One line in `kubernetes/apps/home-automation/n8n/app/helmrelease.yaml`:
`values.image.tag: "2.44.5" -> "2.46.6"`. This is the same change as Renovate PR
#476 (verified 2026-11-08: the PR diff is exactly that one line, `main`-based,
MERGEABLE/CLEAN). No chart, env, PVC or route change.

**Why the plan was retargeted.** `n8n-fleet-2.44.6` pinned the Docker `stable`
digest `sha256:d02752c6...`. The NOW run of 2026-11-06 aborted at preflight
because `stable` had moved: Docker Hub `n8nio/n8n:stable` was pushed again on
2026-11-04T13:11Z and now equals `2.46.6` (`sha256:8602f5df...`), as does the
npm `stable` dist-tag that Renovate's `n8n-stable` custom datasource reads
(`.github/renovate.json5`, customDatasources). The old plan is `superseded`
and never executed, so live is still 2.44.5 and the span is **two minors**
(2.45, 2.46), not a patch.

### 1.2 The fleet, measured live 2026-11-08

| Item | Value |
|---|---|
| Workload | `deployment/n8n` only, 1 replica, ns `home-automation`. `worker.enabled=false`, `webhook.enabled=false`, `valkey.enabled=false` in the HelmRelease; no such deployments exist. Executions mode is regular (main process, `N8N_RUNNERS_MODE=internal`). |
| Image / digest | `n8nio/n8n:2.44.5`, imageID `sha256:bcb4e4917141f4a5249c8eadf2776d347f4c2ede75adfbbc82064826af9a8ead`, node `v26.10.0` |
| Chart | `n8n` 2.1.1 from HelmRepository `n8n` (flux-system), `maxHistory: 2`, `upgrade.remediation.retries: 3` |
| Storage | `pvc/n8n-config`, 5Gi RWO `longhorn-static`, PV `n8n-config` reclaim `Retain`, Longhorn volume `n8n-config` healthy, 2 replicas, 507 MB used. **Embedded SQLite**: `database.sqlite` 512,512,000 B + `-wal` 19 MB; `config` (56 B, holds the encryption key). No DB_TYPE env. |
| Backups | Longhorn `daily-backup-all-volumes` (ns storage); newest Completed Backup CR `backup-3bb4f8ecc7d14b4c`, snapshot 2026-11-08T00:25:16Z. |
| Content | 15 workflows; 8 are `active` but ALL 8 are also `isArchived` (sub-workflow stubs); 0 published/draft workflows indexed at boot (log: "Processed 0 draft workflows, 0 published workflows"); active-id cksum `3124227881 136`. Inactive ones: chat/telegram agents, one MCP-trigger workflow with a POST webhook (auth none), two schedule workflows. |
| Probes | startupProbe `/healthz` 10 s x 30 failures (= **300 s** to come up), then liveness `/healthz` x3, readiness `/healthz/readiness` x3. |
| Exposure | `httproute/n8n` on Gateway `envoy-external` (internet-facing), no SecurityPolicy, no Authentik: n8n authenticates in-app (owner account, `authenticationMethod: email`). `/healthz` over the public edge = 200 today. |
| Quirk (pre-existing) | `Invalid number value for N8N_PORT: tcp://10.96.45.65:5678` is printed by every CLI call: the Service named `n8n` injects `N8N_PORT` via service links into the pod. Harmless on 2.44.5. The rehearsal pod disables service links, so it does NOT prove 2.46.6 tolerates the live pod's env; V4 does. |

**Dependents (what could break).** Measured, not assumed:
- Home Assistant: `grep -ril n8n /config` over its YAML/JSON = no hit; HA does not call n8n.
- Authentik forward-auth: none (route comment + no SecurityPolicy).
- OpenClaw: its `skills-configmap` is SOPS-encrypted and the planner did not
  decrypt it; **unmeasured**, treat as "may call n8n over the in-cluster
  Service or public host". With 0 published workflows there is no production
  webhook for it to hit (the only webhook workflow is inactive), so impact
  during the outage is nil unless it drives the REST/MCP API.
- Envoy access log (2000 lines): one n8n line, a planner probe. No steady client.
- MCP: the `mcpTrigger` workflow is inactive; nothing serves MCP today.
Conclusion: low user-visible blast radius, but the data (workflows, credentials,
encryption key) is irreplaceable, hence the backup-heavy shape.

### 1.3 Why this is not auto-safe, and what is forward-only

- Deny rule `*n8nio/n8n*` has `max: patch` (`runbooks/auto-update-policy.yaml`),
  so a minor is PLAN lane by design (beta channel hazard). PR #476 is a minor
  and is correctly held. Its target IS the stable line here (checked in §2.1).
- **23 new migration files** between `n8n@2.44.5` and `n8n@2.46.6` (list from
  GitHub contents API, `packages/@n8n/db/src/migrations/{common,sqlite}`):
  20 in `common/` (e.g. `MigrateAgentMcpToolPermissions`, `CreateSkillsHubTables`,
  `CreatePromotionRunAndReviewTables`, `ReplacePromotionConnectionsWithEnvironments`,
  `CreateApps`, self-healing tables, `AddKindToUserTable`,
  `MigrateAgentSkillsToHub` (a DATA migration), `AddSkillMcpAvailability`) and 3
  in `sqlite/`. `DeleteInstanceAgentsOnRevert` deletes data on its `down()`.
  The Postgres-only `ExpandNodeIdColumns` does not apply (SQLite).
  The live DB has 302 applied migrations (newest
  `AddTimeoutSecondsToScheduler1791542683581`); after the bump the newest must
  be `AddSkillMcpAvailability1793000146414`.
  There is no supported downgrade: `n8n db:revert` undoes ONE migration at a
  time and its `down()` for the data migrations is destructive. **Rollback is
  therefore restore-from-backup (`rollback_class: backup-restore`).**
- `.github` release notes (CHANGELOG at `n8n@2.46.6`) for 2.45.0, 2.46.0..2.46.6
  (and the 2.44.6/2.44.7, 2.45.4..2.45.7 backports) contain **no entry marked
  BREAKING** and no removed env var that this HelmRelease sets. Relevant items
  read in full and judged:
  - "Remove unused `N8N_SCHEDULER_MIN_INTERVAL` setting (#41194)": not set here.
  - "Turn off expression spans by default (#41211)", "Disable Node Web Storage in
    JS task runners (#41852)": runner/expression internals, no config here.
  - "Authenticate Webhook and MCP Trigger nodes through trusted sources (#41455)":
    adds a dropdown only in the *n8n User Auth (OAuth2)* mode; the one webhook
    workflow here uses `authentication: none` and is inactive. Unaffected.
  - "Make granular credential sharing always on (#41376)": a permission-model
    change for credentials; single-owner instance, but it is why the owner should
    open Credentials once after the bump (§4 V9, human step).
  - Several v3 "migration report" features: informational UI, v3 is not this bump.
  - Runtime Node moves 26.10.0 -> 26.12.1 (`docker/images/n8n/Dockerfile`).
  - `docker/images/*` and the task-runner image are otherwise unchanged in shape
    (entrypoint `tini -- /docker-entrypoint.sh`, `USER node`), so the existing
    Deployment args/probes still apply.
- **Two clocks decide whether the migration survives, and BOTH default to 5 minutes.**
  (1) The startupProbe: chart default `failureThreshold: 30` x `periodSeconds: 10`
  = 300 s (live deployment confirms 30). (2) `HelmRelease.spec.timeout`:
  **unset on this HelmRelease (live `.spec.timeout` is empty) = Helm's default
  5 min**, and that clock also covers scheduling, the image pull and the
  Longhorn attach, so it expires BEFORE the probe does. The old pod is stopped
  (Recreate) and the new one runs all 23 migrations before it listens on :5678.
  A migration that outlasts either clock is killed or declared failed, and with
  the live `upgrade.remediation.retries: 3` Helm then ROLLS BACK: it kills the
  migrating pod and redeploys **2.44.5 over an already (partly) migrated
  database**, and `flux suspend` cannot stop a rollback that is already in flight.
  **This plan therefore removes the hazard at its root, in the SAME commit as the
  tag change** (§3.2), instead of racing it:
  - `spec.timeout: 40m` (Helm's deadline, was the 5 min default);
  - `values.main.startupProbe.failureThreshold: 180` (180 x 10 s = 1800 s = 30 min,
    inside the 40 m budget; chart path verified by rendering chart 2.1.1: the key
    appears on the main container only);
  - **`spec.upgrade.remediation.retries: 0`** (was 3) and
    **`spec.upgrade.cleanupOnFail: false`** (was true). With no retries a failed
    or timed-out upgrade leaves the HelmRelease `Ready=False/UpgradeFailed` and
    Helm NEVER rolls back: there is no rollback leg, so the failure-path ceiling
    is the single 40 m upgrade deadline (+ margin). The block has no
    `strategy`/`remediateLastFailure` key to remove (verified: the live upgrade
    block is exactly `cleanupOnFail: true` + `remediation.retries: 3`).
  Gates: §3.2b (local parse of the edited file, plus a helm render of the probe)
  and §3.4a (live HelmRelease and Deployment). **These are for this window only:**
  the next step after a successful soak is §3.5, which restores `retries: 3` and
  `cleanupOnFail: true`; the failure path's `git revert` restores them as well.
  Without remediation a broken boot would otherwise sit unattended, which is
  acceptable only because this plan runs attended and every failure path begins
  with `flux suspend` (§3.4b, §5).
- **`flux suspend` is not a cancel button** (any cause: readiness never reached,
  ErrImagePull, crash loop). It blocks new reconciles; an upgrade action already
  running continues to its deadline. With retries 0 that action simply ends in
  `UpgradeFailed` and nothing follows, and §5 R1b waits for exactly that before
  anyone touches the volume.

### 1.4 Honest risk statement

Risk is `medium`, not high: SQLite file is small, the instance has no published
workflow so nothing fires or is missed while it is down, the encrypted
credentials stay decryptable because the key lives in the same PVC (`config`)
that is restored together, and the rehearsal on a restored copy of the real
data with the real digest happens first. It is not `low` because the migration
set is large, forward-only, includes a data migration, and the restart is
bound by two timers (Helm timeout, startupProbe) that this plan widens. `capability_change: true` and `rollback_class: backup-restore`
route it to a human-gated, operator-present window; **no SD-10 pre-approval**.

## 2) Pre-checks

Run all premises first (`.venv/bin/python3 runbooks/plan-premises.py n8n-fleet-2.46.6 --require-premises`). Then, in order:

### 2.1 Resolve the target from the same source Renovate/the window agent use, and assert tag == digest

Fail-closed: any empty fetch, any disagreement, any pin mismatch prints `FAIL`.
This is the check that was missing on 2026-11-06 (the old plan only compared
Docker `stable` against a pinned digest; here npm `stable`, Docker `stable` and
Docker `2.46.6` must all agree with the pin).

```bash
hubdigest() { curl -s "https://hub.docker.com/v2/repositories/n8nio/n8n/tags/$1" | python3 -c "import sys,json; print(json.load(sys.stdin).get('digest',''))"; }
PIN=sha256:8602f5dfacbe2c931eeafd010de0e68182310e9f309921e780ab69182e92b3ae
NPM=$(curl -s https://registry.npmjs.org/-/package/n8n/dist-tags | python3 -c "import sys,json; print(json.load(sys.stdin).get('stable',''))")
D_STABLE=$(hubdigest stable); D_TGT=$(hubdigest 2.46.6)
echo "npm-stable=$NPM  docker-stable=$D_STABLE  docker-2.46.6=$D_TGT"
if [ "$NPM" = "2.46.6" ] && [ -n "$D_TGT" ] && [ "$D_TGT" = "$D_STABLE" ] && [ "$D_TGT" = "$PIN" ]; then echo PASS; else echo FAIL; fi
```
PASS: last line `PASS` (measured 2026-11-08: all three values agree on `2.46.6` /
`sha256:8602f5df...`). Dry-tested with the pin altered to `00000000...`: prints `FAIL`.
FAIL covers: `stable` moved to a newer release (STOP, retarget; do **not** float
to the new stable inside the window), a dead registry (empty strings), or a
re-pushed tag. Also confirm the beta line is not what you are installing:
`curl -s https://registry.npmjs.org/-/package/n8n/dist-tags` must show
`beta`/`next` ahead of `stable` (2.47.2 today), never equal to it.

```bash
# 2.1b PR 476 is still the same one-line change (gh is refused inside premises)
gh pr view 476 --json state,mergeable,title -q '[.state,.mergeable,.title]|@tsv'
gh pr diff 476 | grep -c '^[+-][^+-]'
```
PASS: `OPEN	MERGEABLE	chore(deps): update n8nio/n8n docker tag to v2.46.6` and `2`
(one removed, one added line). Anything else: PR was rebased onto another
change or retargeted; re-read the diff before using the §3 edit.

### 2.2 Flux and cluster calm

```bash
flux get helmreleases -n home-automation n8n
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
kubectl get pods -n home-automation -l app.kubernetes.io/name=n8n
kubectl get volumes.longhorn.io -n storage -l restore-proof=true --no-headers | wc -l
```
PASS: HR `True`; no non-Ready kustomization in `flux-system`/`home-automation`;
one `Running 1/1` pod; the last line is `0` (no leftover scratch volume). STOP on any miss.

### 2.3 Baseline of CONTENTS (record every value)

```bash
cd /Users/mu/code/cberg-home-nextgen
kubectl exec -n home-automation deploy/n8n -- n8n --version
kubectl exec -n home-automation deploy/n8n -- node --version
kubectl exec -n home-automation deploy/n8n -- sh -c "n8n list:workflow --onlyId 2>/dev/null | grep -E '^[A-Za-z0-9]{16}\$' | wc -l"
kubectl exec -n home-automation deploy/n8n -- sh -c "n8n list:workflow --active=true --onlyId 2>/dev/null | grep -E '^[A-Za-z0-9]{16}\$' | sort | cksum"
kubectl logs -n home-automation deploy/n8n | grep -c 'Processed 0 draft workflows, 0 published workflows'
kubectl port-forward -n home-automation svc/n8n 15678:5678 >/dev/null 2>&1 & PF=$!; sleep 4
curl -s localhost:15678/rest/settings | python3 -c "import sys,json; d=json.load(sys.stdin); d=d.get('data',d); print('setup=',d['userManagement']['showSetupOnFirstLoad'])"
curl -s -o /dev/null -w 'login-unauth=%{http_code}\n' localhost:15678/rest/login
kill $PF
```
Measured 2026-11-08: `2.44.5`, `v26.10.0`, `15`, `3124227881 136`, grep count `1`
(a restarted pod prints it once; if `0`, a workflow got published since: re-read
§1.2), `setup= False`, `login-unauth=401`. Re-measure at window time. A `0` count
is a broken baseline, not a pass.

### 2.4 Rehearsal prerequisite: the pod must publish nothing

Because the §2.6 scratch pod boots a COPY of the real data, any *published*
workflow would activate there too (Telegram pollers, schedules) and duplicate
real side effects. The baseline line `Processed 0 ... 0 published workflows`
above is the precondition: **if it is not exactly 1 match, skip §2.6 and ask
the operator**; do not rehearse.

### 2.5 Backup (backup_gate a + b)

```bash
set -o pipefail
# (b0) where the Mac-side evidence goes (outside the repo; holds encrypted credentials AND the key => mode 700)
B=$HOME/n8n-backups/pre-2.46.6-$(date +%Y%m%d-%H%M); mkdir -p "$B" && chmod 700 "$B"
# (a) newest CONFIRMED Longhorn backup of n8n-config, age gate via the shared helper (never an inline status.volumeName filter:
#     the nightly Backup CR can sit Completed with status.volumeName='' for hours). Exit 0 = FRESH, 1 = STALE/NONE, 2 = lookup error.
.venv/bin/python3 runbooks/longhorn-backup-age.py n8n-config --max-hours 26 | tee "$B/longhorn-backup"
grep -q ' FRESH ' "$B/longhorn-backup" || { echo "STOP: newest n8n-config backup is not FRESH (<=26h)"; exit 1; }
# (b) Mac-side copy of the DB
kubectl exec -n home-automation deploy/n8n -- tar cf - -C /home/node/.n8n database.sqlite database.sqlite-wal database.sqlite-shm config > "$B/n8n.tar"
ls -l "$B/n8n.tar"; tar tf "$B/n8n.tar" | wc -l
mkdir "$B/x" && tar xf "$B/n8n.tar" -C "$B/x"
sqlite3 "$B/x/database.sqlite" "PRAGMA integrity_check; select count(*) from workflow_entity; select count(*) from migrations; select name from migrations order by id desc limit 1;"
echo "BACKUP_DIR=$B"
```
PASS (measured 2026-11-08 against the live pod): (a) the helper prints
`n8n-config 20.2h FRESH via backup-cr backup=backup-3bb4f8ecc7d14b4c at=2026-11-08T00:25:16Z`
and exit 0 (the line is recorded in `$B/longhorn-backup` for §5 Path B). Negative
controls, run live: a wrong volume name (`n8n-confg`) prints `ERROR: no Longhorn
volume named 'n8n-confg'` and exits 2; `--max-hours 0.1` prints `... STALE ...` and
exits 1; either leaves the `grep ' FRESH '` gate failing, so the block stops; (b) tar size `531846656` (gate
>= 500000000; a truncated stream is a few KB), `4` entries, and sqlite3 prints
`ok`, `15`, `302`, `AddTimeoutSecondsToScheduler1791542683581`. The sqlite3
check is the real gate: a corrupt or half-streamed copy cannot print `ok` + 15
rows. If (a) is older than 26 h run
`kubectl create job --from=cronjob/daily-backup-all-volumes pre-n8n-2466-$(date +%Y%m%d-%H%M) -n storage`
(backs up ALL volumes; heavy; say so in the window log) and wait for a NEW
Completed CR for `n8n-config` created after the command. Keep `$B` for 7 days
after a clean soak, then `rm -rf` it. **Caveat:** the live tar reads
`database.sqlite`, `-wal` and `-shm` one after another from a running process,
so it CAN be torn; `integrity_check` plus the row counts catch that, and a failed
check means re-take it (n8n is idle, so a retry normally passes). The Longhorn
Backup CR (a) is the real fallback (rollback Path B), not this tar.

### 2.6 Rehearsal on a restore of the real data with the real digest (backup_gate c)

Creates ONLY objects named `n8n-rp-<mmddHHMM>` labelled `restore-proof=true`
(Longhorn Volume, PV, PVC, Pod). It never touches `n8n-config`. Pattern and
manifests are lifted from `runbooks/backup-restore-proof.py` (proven for
postgres; this is its SQLite variant, **not yet executed by the planner, because
the planner is read-only**: the window agent must treat a failure of the
scaffolding itself as "fix the scratch step", not as a verdict on the upgrade).

```bash
cd /Users/mu/code/cberg-home-nextgen
RP=n8n-rp-$(date +%m%d%H%M); NS=home-automation
IMG=n8nio/n8n:2.46.6@sha256:8602f5dfacbe2c931eeafd010de0e68182310e9f309921e780ab69182e92b3ae
# newest CONFIRMED backup via the shared helper (same freshness bound as 2.5a), then its restore URL
BK=$(.venv/bin/python3 runbooks/longhorn-backup-age.py n8n-config --max-hours 26 --json | python3 -c 'import sys,json; r=json.load(sys.stdin)[0]; print(r["backup"] if r["verdict"]=="FRESH" else "")')
test -n "$BK" || { echo "FAIL: no FRESH backup of n8n-config"; exit 1; }
URL=$(kubectl get backups.longhorn.io "$BK" -n storage -o jsonpath='{.status.url}')
test -n "$URL" || { echo "FAIL: backup $BK has no url yet (unsynced CR): wait and retry"; exit 1; }
echo "restoring from $BK"

# 1 scratch volume FROM the backup
kubectl apply -f - <<EOF
apiVersion: longhorn.io/v1beta2
kind: Volume
metadata: {name: $RP, namespace: storage, labels: {restore-proof: "true"}}
spec: {fromBackup: "$URL", numberOfReplicas: 1, frontend: blockdev}
EOF
# 2 wait for the restore (bounded 15 min)
for i in $(seq 1 90); do
  S=$(kubectl get volumes.longhorn.io -n storage $RP -o jsonpath='{.status.state}/{.status.restoreRequired}')
  [ "$S" = "detached/false" ] && break; sleep 10
done; echo "restore-state=$S"; test "$S" = "detached/false" || { echo "FAIL restore"; false; }

# 3 PV + PVC + pod (service links OFF: the live pod's N8N_PORT service-link env is not reproduced here)
kubectl apply -f - <<EOF
apiVersion: v1
kind: PersistentVolume
metadata: {name: $RP, labels: {restore-proof: "true"}}
spec:
  capacity: {storage: 5Gi}
  accessModes: [ReadWriteOnce]
  persistentVolumeReclaimPolicy: Retain
  storageClassName: longhorn-static
  csi: {driver: driver.longhorn.io, volumeHandle: $RP, fsType: ext4}
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata: {name: $RP, namespace: $NS, labels: {restore-proof: "true"}}
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: longhorn-static
  volumeName: $RP
  resources: {requests: {storage: 5Gi}}
---
apiVersion: v1
kind: Pod
metadata: {name: $RP, namespace: $NS, labels: {restore-proof: "true"}}
spec:
  restartPolicy: Never
  enableServiceLinks: false
  securityContext: {runAsUser: 1000, runAsGroup: 1000, fsGroup: 1000, runAsNonRoot: true}
  containers:
    - name: n8n
      image: $IMG
      env:
        - {name: N8N_RUNNERS_MODE, value: internal}
        - {name: DB_SQLITE_POOL_SIZE, value: "5"}
        - {name: N8N_PROTOCOL, value: http}
      volumeMounts: [{name: data, mountPath: /home/node/.n8n}]
      resources: {requests: {cpu: 100m, memory: 512Mi}, limits: {cpu: 500m, memory: 1Gi}}   # = the live pod
  volumes: [{name: data, persistentVolumeClaim: {claimName: $RP}}]
EOF
# 4 time to readiness (this includes all 23 migrations). T0 starts when the container is RUNNING,
#   i.e. after scheduling, attach and image pull, so the figure is boot+migration only.
for i in $(seq 1 120); do
  kubectl get pod $RP -n $NS -o jsonpath='{.status.containerStatuses[0].state.running.startedAt}' | grep -q . && break; sleep 5
done
T0=$SECONDS; R=0
while [ $((SECONDS-T0)) -lt 900 ]; do
  kubectl exec -n $NS $RP -- wget -qO- http://localhost:5678/healthz/readiness 2>/dev/null | grep -q '"ok"' && { R=1; break; }; sleep 5
done
echo "ready=$R after $((SECONDS-T0))s"
```
PASS: `ready=1` and `after <=300s`. `ready=0` (900 s loop exhausted) or a longer
time: **STOP the upgrade**. This can fail: a bad migration or an unreadable DB
never answers readiness, exactly like the live boot would. **State plainly: this
figure is an OPTIMISTIC bound.** The scratch volume has 1 replica (live has 2,
so live writes are slower), the DB was just restored (warm), and nothing else
loads the node. That is why the live budgets are 1800 s (probe) and 40 m (Helm),
6x the PASS bound, instead of the old 300 s: a rehearsal time under 300 s leaves
a generous live margin; a time between 300 s and 900 s is a hold-and-ask, not a
pass.

```bash
# 5 contents on the migrated COPY
kubectl exec -n $NS $RP -- node --version                                              # expect v26.12.1 (feeds V3; not measured before the rehearsal)
kubectl exec -n $NS $RP -- n8n --version 2>&1 | tail -1                                # expect 2.46.6
kubectl logs -n $NS $RP | grep -c 'Version: 2.46.6'                                   # expect 1
kubectl logs -n $NS $RP | grep -c 'Processed 0 draft workflows, 0 published workflows' # expect 1 (nothing activated)
kubectl exec -n $NS $RP -- sh -c "n8n list:workflow --onlyId 2>/dev/null | grep -E '^[A-Za-z0-9]{16}\$' | wc -l"                       # expect 15
kubectl exec -n $NS $RP -- sh -c "n8n list:workflow --active=true --onlyId 2>/dev/null | grep -E '^[A-Za-z0-9]{16}\$' | sort | cksum"  # expect 3124227881 136
# 6 smoke EXECUTION with a negative control. The control runs BEFORE the import and must NOT show the marker.
kubectl exec -n $NS $RP -- n8n execute --id=rpsmoke000000001 2>&1 | grep -c 'rp-smoke-ok'    # control: expect 0
kubectl exec -i -n $NS $RP -- sh -c 'cat > /tmp/smoke.json' <<'EOF'
[{"id":"rpsmoke000000001","name":"rp-smoke","active":false,"nodes":[{"id":"a1","name":"Start","type":"n8n-nodes-base.manualTrigger","typeVersion":1,"position":[0,0],"parameters":{}},{"id":"a2","name":"Mark","type":"n8n-nodes-base.set","typeVersion":3.4,"position":[220,0],"parameters":{"assignments":{"assignments":[{"id":"b1","name":"proof","value":"rp-smoke-ok","type":"string"}]},"options":{}}}],"connections":{"Start":{"main":[[{"node":"Mark","type":"main","index":0}]]}},"settings":{}}]
EOF
kubectl exec -n $NS $RP -- n8n import:workflow --input=/tmp/smoke.json 2>&1 | tail -2
kubectl exec -n $NS $RP -- n8n execute --id=rpsmoke000000001 2>&1 | grep -c 'rp-smoke-ok'    # expect >=1
# 7 teardown, ALWAYS (guarded so it can only ever delete n8n-rp-* objects)
case "$RP" in n8n-rp-*) kubectl delete pod/$RP pvc/$RP -n $NS --ignore-not-found --timeout=120s; kubectl delete pv/$RP --ignore-not-found --timeout=120s; kubectl delete volumes.longhorn.io $RP -n storage --ignore-not-found --timeout=120s;; esac
kubectl get volumes.longhorn.io -n storage -l restore-proof=true --no-headers | wc -l     # expect 0
```
PASS: `v26.12.1`, `2.46.6`, `1`, `1`, `15`, `3124227881 136`, control `0`, then `>=1` for the marker
(the smoke JSON proves a real execution through the migrated engine; the control
proves the marker is absent until the workflow exists, so a `grep` that matches
everything cannot pass), and the final count `0`. The smoke workflow is
imported into the SCRATCH copy only; the volume is destroyed. **The smoke JSON
and `n8n execute` flags were taken from the live CLI help but not run by the
planner**; if import or execute rejects the file, fix the JSON (n8n's own
`n8n export:workflow` output is the reference shape) and keep the control. Also
record the scratch migrations check if desired: `kubectl exec ... -- sh -c`
has no sqlite3; the authoritative migration assertion is V6 on the live pod.

## 3) Steps

Only after §2 passed in full.

```bash
cd /Users/mu/code/cberg-home-nextgen
# 3.1 sync
git fetch origin main && git merge --ff-only origin/main

# 3.2 THREE edits in ONE commit. Dry-tested on a scratch copy of helmrelease.yaml with BSD sed + awk, 2026-11-08.
F=kubernetes/apps/home-automation/n8n/app/helmrelease.yaml
#   (i) the tag            31c31  <       tag: "2.44.5"  --->       tag: "2.46.6"
sed -i '' 's/^\([[:space:]]*tag: \)"2\.44\.5"$/\1"2.46.6"/' $F
#   (ii) Helm's deadline    +  timeout: 40m                         (after `  interval: 30m`, line 8)
#   (iii) the startup probe +  main.startupProbe.failureThreshold: 180   (after `      replicaCount: 1`, line 74)
#   (iv) no Helm rollback   cleanupOnFail true -> false ; remediation.retries 3 -> 0  (upgrade block ONLY; install.retries stays 1)
sed -i '' 's/^\(    cleanupOnFail: \)true$/\1false/' $F
sed -i '' 's/^\(      retries: \)3$/\10/' $F
awk '{print} /^  interval: 30m$/ {print "  timeout: 40m"} /^      replicaCount: 1$/ {print "      startupProbe:"; print "        httpGet:"; print "          path: /healthz"; print "          port: http"; print "        periodSeconds: 10"; print "        failureThreshold: 180"}' $F > $F.new && mv $F.new $F
git diff --stat $F    # 1 file, 10 insertions, 3 deletions
git diff $F | grep '^[+-][^+-]'
```
Expected diff lines (exactly): `-      tag: "2.44.5"`, `+      tag: "2.46.6"`,
`-    cleanupOnFail: true`, `+    cleanupOnFail: false`, `-      retries: 3`, `+      retries: 0`, `+  timeout: 40m`,
`+      startupProbe:`, `+        httpGet:`, `+          path: /healthz`,
`+          port: http`, `+        periodSeconds: 10`, `+        failureThreshold: 180`.
`httpGet`/`periodSeconds` restate the chart defaults (Helm would merge them
anyway: rendering `failureThreshold` alone kept `httpGet`); writing them out keeps
the probe self-describing and identical to today's apart from the threshold.

```bash
# 3.2b GATE: the widening AND the no-rollback setting are in the edited file, BEFORE the push (fails if a sed/awk missed)
# WINDOW AGENT: use YOUR OWN scratch directory for the values file below (the path shown is the planner's session scratchpad)
python3 -c "
import yaml
d=yaml.safe_load(open('$F'))['spec']
r=d['upgrade']['remediation']
print('timeout=',d.get('timeout'),'| ft=',d['values']['main']['startupProbe']['failureThreshold'],'| tag=',d['values']['image']['tag'],'| retries=',r.get('retries'),'| cleanupOnFail=',d['upgrade'].get('cleanupOnFail'),'| extra-keys=',sorted(set(r)-{'retries'}),'| install.retries=',d['install']['remediation']['retries'])"
python3 -c "import yaml;print(yaml.safe_dump(yaml.safe_load(open('$F'))['spec']['values']))" > /private/tmp/claude-501/-Users-mu-code-cberg-home-nextgen/2f30f636-724d-446c-82db-799d0bdfc5e3/scratchpad/n8n-values.yaml
helm template n8n oci://8gears.container-registry.com/library/n8n --version 2.1.1 -f /private/tmp/claude-501/-Users-mu-code-cberg-home-nextgen/2f30f636-724d-446c-82db-799d0bdfc5e3/scratchpad/n8n-values.yaml | grep -c 'failureThreshold: 180'
rm -f /private/tmp/claude-501/-Users-mu-code-cberg-home-nextgen/2f30f636-724d-446c-82db-799d0bdfc5e3/scratchpad/n8n-values.yaml
```
PASS: `timeout= 40m | ft= 180 | tag= 2.46.6 | retries= 0 | cleanupOnFail= False | extra-keys= [] | install.retries= 1` and a render count of `1`
(measured 2026-11-08 on the scratch copy; the count is `0` on today's file, where
the threshold renders as 30, so a missed edit fails the gate). Do not push
otherwise.

```bash
# 3.3 commit ONLY this path (shared worktree), verify the subject, push
MSG=$(mktemp -t n8n-msg)
printf 'fix(container): update n8nio/n8n ( 2.44.5 -> 2.46.6 ) and widen HR timeout + startupProbe (plan n8n-fleet-2.46.6, supersedes #476)\n\nNewest stable (npm dist-tag stable == docker :stable == 2.46.6). 23 forward-only migrations; backups and a scratch rehearsal passed first. timeout 40m and startupProbe 1800s so Helm cannot roll back mid-migration.\n\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>\n' > "$MSG"
git commit --only $F -F "$MSG"
git log -1 --format=%s          # must be the subject above; amend before push if not
git show --stat HEAD            # exactly 1 file
git push origin main
```
Flux picks it up through the webhook; no manual `flux reconcile`. Renovate
closes #476 by itself once `main` carries 2.46.6; if it is still open after one
Renovate cycle, close it by hand, do NOT merge it.

```bash
# 3.4a GATE: the widening reached the cluster (poll up to ~2 min for Flux to apply the commit)
kubectl get helmrelease -n home-automation n8n -o jsonpath='timeout={.spec.timeout} retries={.spec.upgrade.remediation.retries} cleanup={.spec.upgrade.cleanupOnFail}{"\n"}'
kubectl get deploy -n home-automation n8n -o jsonpath='{.spec.template.spec.containers[0].image} ft={.spec.template.spec.containers[0].startupProbe.failureThreshold}{"\n"}'
```
PASS: `timeout=40m retries=0 cleanup=false` and `n8nio/n8n:2.46.6 ft=180`. Today they read
`timeout= retries=3 cleanup=true` and `n8nio/n8n:2.44.5 ft=30`, so this fails until the commit has landed. If the
Deployment shows `2.46.6` but `ft=30`, or the HelmRelease still reads `retries=3`,
the edit did not apply: **suspend (below) before the pod gets 300 s**.

```bash
# 3.4b watch the Recreate + migration. Bounded at 42 min = the single Helm upgrade deadline (40m) + 2 min margin. No rollback leg (retries 0).
kubectl rollout status deploy/n8n -n home-automation --timeout=2520s
flux get helmreleases -n home-automation n8n
```
PASS: `successfully rolled out` and the HR `True`. **FAILURE (any of: timeout,
`CrashLoopBackOff`, `ErrImagePull`, `Multi-Attach`, restartCount > 0, HR
`Ready=False`/`Unknown` with a failure reason, or §3.4a not PASS): the FIRST
command, before anything else, is**

```bash
flux suspend helmrelease n8n -n home-automation
```
**then go to §5** (R1 is then already done; continue at R2). A migration that is
merely slow (pod `Running 0/1`, restartCount 0, log still moving, under 40 min)
is NOT a failure: with the widened budgets neither Kubernetes nor Helm will act
on it, so wait.

**Budget choice (stated plainly):** `spec.timeout` stays **40m** and the operator
watch waits the **full Helm deadline (42 min with margin)** before calling a
SLOW boot a failure. The startupProbe (180 x 10 s = 1800 s) is shorter than Helm's
deadline, so a boot that never becomes ready is killed by kubelet at about 30 min
and Helm reports it before 40 min. Only a HARD failure (`ErrImagePull`,
`CrashLoopBackOff`, `Multi-Attach`, restartCount > 0) is called early; for those
the suspend is followed by the §5 R1b wait, because `flux suspend` does NOT cancel
a Helm action already in flight (see §5). Normal runs finish in about 8 minutes;
the 42 min figure is the failure-path ceiling (one 40 m deadline; with `retries: 0` Helm never rolls back, so nothing is added after it), after which the restore in §5 takes roughly another 15-20 min: about 60-65 min worst case, inside the 180 min window. `rollout status` can green-light the old generation, so V2 is
the real check.

### 3.5 Post-soak cleanup (separate commit, only after V1-V9 passed and the operator is happy)

The no-rollback settings exist for this window only. Restore them so the next
upgrade of any app-level value gets Flux's normal remediation again:

```bash
F=kubernetes/apps/home-automation/n8n/app/helmrelease.yaml
sed -i '' 's/^\(    cleanupOnFail: \)false$/\1true/' $F
sed -i '' 's/^\(      retries: \)0$/\13/' $F
git diff --stat $F    # 1 file, 2 insertions, 2 deletions
git commit --only $F -m "chore(n8n): restore upgrade.remediation.retries 3 + cleanupOnFail after the 2.46.6 migration window (plan n8n-fleet-2.46.6)"
git log -1 --format=%s && git push origin main
kubectl get helmrelease -n home-automation n8n -o jsonpath='retries={.spec.upgrade.remediation.retries} cleanup={.spec.upgrade.cleanupOnFail} timeout={.spec.timeout}{"\n"}'
```
PASS: `retries=3 cleanup=true timeout=40m` (the 40m timeout and the 180 probe stay:
they only matter during a boot; remove them separately if the operator prefers).
`install.remediation.retries: 1` is never touched (the `retries: 0` pattern matches
only the upgrade block, verified in §3.2b by `install.retries= 1`). Do this within
the same day; leaving `retries: 0` means a failed upgrade of this stateful app never
self-heals. The failure path does not need this step: its `git revert` (R3) restores
`retries: 3` and `cleanupOnFail: true` together with the old tag.

## 4) Verification

CONTROL: metric kube_pod_container_info, the gate reads its `image` label for `namespace="home-automation",container="n8n"`. Exactly 1 series with `docker.io/n8nio/n8n:2.46.6` is required. Measured live 2026-11-08: 1 series (`...:2.44.5`); the negative control `container="n8n-nonexistent"` returned 0 series, so an empty result is detectable and is a FAIL.
CONTROL: metric kube_pod_container_status_restarts_total, `namespace="home-automation",container="n8n"` must read `0` after the 10-minute settle (present live: value 0).
CONTENTS ASSERTION: the workflow inventory (count 15, active cksum `3124227881 136`) AND the migrations table of the live DB (newest `AddSkillMcpAvailability1793000146414`, count >= 322 vs 302 before) both survive/advance. Measured by V5 and V6, compared to §2.3/§2.5.

```bash
# V1 spec
kubectl get deploy -n home-automation n8n -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
```
PASS: `n8nio/n8n:2.46.6`. `2.44.5` = Flux has not applied the commit.

```bash
# V2 the RUNNING pod's digest (rollout status can green-light the old generation)
kubectl get pods -n home-automation -l app.kubernetes.io/name=n8n -o jsonpath='{range .items[*]}{.metadata.name} {.status.containerStatuses[0].imageID}{"\n"}{end}'
```
PASS: exactly one pod, imageID ending
`sha256:8602f5dfacbe2c931eeafd010de0e68182310e9f309921e780ab69182e92b3ae`, the
digest the §2.6 rehearsal ran. `bcb4e491...` = still the old image; `83ec9349...`
= the BETA image was pulled, roll back at once.

```bash
# V3 binary, runtime, and boot log of THIS pod
kubectl exec -n home-automation deploy/n8n -- n8n --version
kubectl exec -n home-automation deploy/n8n -- node --version
kubectl logs -n home-automation deploy/n8n | grep -c -e 'Version: 2.46.6' -e 'Registered runner "JS Task Runner"'
kubectl get pods -n home-automation -l app.kubernetes.io/name=n8n -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}{"\n"}'
```
PASS: `2.46.6`, `v26.12.1`, a count of `2` (version banner + task runner
registered, both printed by the live 2.44.5 pod today in the same format), restartCount `0`.
The old pod prints `2.44.5`/`v26.10.0` and a banner that does not match (count `1`).

```bash
# V4 serving: liveness + DB-migrated readiness, over the pod AND the public edge, with a negative control
kubectl port-forward -n home-automation svc/n8n 15678:5678 >/dev/null 2>&1 & PF=$!; sleep 4
curl -s -o /dev/null -w 'healthz=%{http_code}\n'   localhost:15678/healthz
curl -s -o /dev/null -w 'readiness=%{http_code}\n' localhost:15678/healthz/readiness
curl -s localhost:15678/rest/settings | python3 -c "import sys,json; d=json.load(sys.stdin); d=d.get('data',d); print('setup=',d['userManagement']['showSetupOnFirstLoad'])"
curl -s -o /dev/null -w 'login-unauth=%{http_code}\n' localhost:15678/rest/login
kill $PF
HOST=$(kubectl get httproute -n home-automation n8n -o jsonpath='{.spec.hostnames[0]}')
curl -s -o /dev/null -w 'edge-healthz=%{http_code}\n' https://$HOST/healthz
curl -s https://$HOST/webhook/rp-negctl | grep -ci 'webhook'
```
PASS: `healthz=200`, `readiness=200`, `setup= False`, `login-unauth=401`,
`edge-healthz=200`, and the last line `>=1`. This is the *webhook path*
gate: no production webhook workflow is published, so the path cannot be
exercised end to end (HA does not call n8n, §1.2). What CAN be proven is that
n8n's webhook router answers through envoy-external: an unknown path must return
n8n's own JSON ("The requested webhook ... is not registered", measured today),
which contains the word *webhook*; an envoy no-route or 503 returns an empty
body (count `0`) and FAILS. `setup= True` means n8n booted on an EMPTY database
(first-run wizard), the worst case: go to §5. `readiness=503` = process up, DB
not connected/migrated. Note `/healthz-nope`-style paths return 200 (SPA
fallback), so never use an unknown *non-webhook* path as a negative control.

```bash
# V5 CONTENTS: workflow inventory vs 2.3
kubectl exec -n home-automation deploy/n8n -- sh -c "n8n list:workflow --onlyId 2>/dev/null | grep -E '^[A-Za-z0-9]{16}\$' | wc -l"
kubectl exec -n home-automation deploy/n8n -- sh -c "n8n list:workflow --active=true --onlyId 2>/dev/null | grep -E '^[A-Za-z0-9]{16}\$' | sort | cksum"
kubectl logs -n home-automation deploy/n8n | grep -c 'Processed 0 draft workflows, 0 published workflows'
```
PASS: `15`, `3124227881 136`, `1`. A different cksum = a workflow was
deactivated or lost on boot; `0` is a FAIL.

```bash
# V6 CONTENTS: the live DB really migrated (no sqlite3 in the pod; stream a copy to the Mac, same recipe as 2.5)
set -o pipefail
B2=$(mktemp -d); kubectl exec -n home-automation deploy/n8n -- tar cf - -C /home/node/.n8n database.sqlite database.sqlite-wal database.sqlite-shm | tar xf - -C "$B2"
sqlite3 "$B2/database.sqlite" "PRAGMA integrity_check; select count(*) from workflow_entity; select count(*) from migrations; select name from migrations order by id desc limit 1;"
rm -rf "$B2"
```
PASS: `ok`, `15`, a number `>= 322`, `AddSkillMcpAvailability1793000146414`. The
same query on the pre-upgrade copy (§2.5) returned `302` /
`AddTimeoutSecondsToScheduler1791542683581`, so the gate discriminates between
"migrated" and "still old schema". `integrity_check` other than `ok` = restore (§5).

```bash
# V7 Prometheus (kube-state-metrics only) after a 10 min settle
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 4
curl -s --data-urlencode 'query=kube_pod_container_info{namespace="home-automation",container="n8n"}' http://localhost:19090/api/v1/query \
  | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print(len(r), [x['metric'].get('image') for x in r])"
curl -s --data-urlencode 'query=kube_pod_container_status_restarts_total{namespace="home-automation",container="n8n"}' http://localhost:19090/api/v1/query \
  | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print(len(r), [x['value'][1] for x in r])"
kill $PF
```
PASS: `1 ['docker.io/n8nio/n8n:2.46.6']` and `1 ['0']`. `0 []` = no data, a FAIL
(check kube-state-metrics before concluding).

**V8 queue/worker health.** Not applicable by design: premise
`single-replica-main-only` (no worker/webhook/valkey deployments) plus
`N8N_RUNNERS_MODE=internal`; the internal JS task runner's registration is in the
V3 log count. If the window agent finds a worker deployment, the plan is void.

**V9 login/SSO (human step, 2 min).** n8n has no SSO here (in-app owner account;
no Authentik). The unauthenticated gates above prove user management is up and
the owner exists (`setup= False`, `login-unauth=401`); a *successful login* needs
the owner password, which the agent does not hold. Operator, in Chrome: open the
n8n host, sign in, open **Credentials** once (granular credential sharing is
always-on from 2.45) and confirm the existing credentials list and one workflow
open. Record the result via `home-operation decide`. The window agent must not
mark the plan executed on V1-V8 alone if the operator is present and has not done it.

**V10 security finding re-read.** After the next sweep, `runbooks/policy-cli.py
finding show F-d8bf68df`: if the image no longer carries it, close it with
`--commit <sha of 3.3>`; if it does, leave it open and say the bump did not clear
it (do not claim it).

## 5) Rollback

Forward-only migrations (§1.3): **a bare `git revert` is NOT a rollback.** It
redeploys 2.44.5 against a database 2.46.6 has already migrated. §3.2 sets
`upgrade.remediation.retries: 0` so Helm itself will not roll back, but the
order below stays mandatory as defense in depth: **freeze Flux, wait until
helm-controller is idle, empty the volume of pods, restore data, THEN land git,
THEN resume.** No step may run while a 2.44.5 pod could
start on the migrated DB, nor while a pod and the restore pod could both attach
the RWO volume.

```bash
cd /Users/mu/code/cberg-home-nextgen
# R1 FIRST, always. Stops Helm remediation and any reconcile from creating pods.
flux suspend helmrelease n8n -n home-automation
# R1b WAIT FOR TERMINAL (defense in depth: with retries 0 there is no rollback leg, but a Helm action may
#     still be in flight, and `flux suspend` does NOT cancel it). Cap 45 min = the 40m upgrade deadline + margin;
#     valid because nothing follows the upgrade (no rollback leg). Save this block to a file and run it with
#     `bash <file>` so the STOP below really stops the run.
NS=home-automation; OKN=0; SIGP=""; T=0
for i in $(seq 1 270); do
  R=$(kubectl get helmrelease n8n -n $NS -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}/{.status.conditions[?(@.type=="Ready")].reason}' 2>/dev/null)
  ROWS=$(kubectl get secret -n $NS -l owner=helm,name=n8n --no-headers -o custom-columns=V:.metadata.labels.version,S:.metadata.labels.status 2>/dev/null)
  NR=$(printf '%s\n' "$ROWS" | grep -c '[0-9]')
  P=$(printf '%s\n' "$ROWS" | grep -c -e pending-upgrade -e pending-rollback)
  TOP=$(printf '%s\n' "$ROWS" | awk '{print $1}' | sort -n | tail -1)
  SIG="$(kubectl get helmrelease n8n -n $NS -o jsonpath='{.metadata.generation}/{.status.lastReleaseRevision}' 2>/dev/null)/$TOP"
  # terminal-looking ONLY if: Ready is a definite True/False with a reason (an empty or unparseable read is NOT),
  # at least one Helm release secret exists, and none is pending
  if printf '%s' "$R" | grep -Eq '^(True|False)/.+' && [ "$NR" -ge 1 ] && [ "$P" -eq 0 ] && [ -n "$TOP" ]; then
    if [ "$SIG" = "$SIGP" ]; then OKN=$((OKN+1)); else OKN=1; fi
    SIGP="$SIG"
  else
    OKN=0; SIGP=""
  fi
  # stable = 7 consecutive polls (>= 60 s) with generation, lastReleaseRevision and newest release secret unchanged
  [ "$OKN" -ge 7 ] && { T=1; break; }
  sleep 10
done
echo "ready=$R rows=$NR pending=$P newest=$TOP stable_polls=$OKN terminal=$T"
kubectl get helmrelease n8n -n $NS -o jsonpath='{range .status.conditions[*]}{.type}={.status}/{.reason}{"\n"}{end}'
[ "$T" -eq 1 ] || { echo "STOP: helm-controller not terminal - do NOT continue to R2"; exit 1; }
```
PASS: `terminal=1` after at least 7 polls (about 60 s). Replayed 2026-11-08 with
the exact block above against a mocked `kubectl` (the planner is read-only):
a NONEXISTENT HelmRelease (empty reads) gives `terminal=0` and `STOP`;
`False/UpgradeFailed` with a fresh `failed` secret that keeps changing revision
keeps resetting the counter and is terminal only after 7 unchanged polls;
the healthy HelmRelease (`True/UpgradeSucceeded`, secrets 65/66, revision 66)
is terminal on poll 7. Terminal states that are fine to proceed from:
`UpgradeFailed` (the expected failure end state with retries 0) or
`UpgradeSucceeded`; everything after this point overwrites the volume anyway.
**Why wait and not restart helm-controller:** a restart kills the action but can
strand the release in `pending-upgrade`, which then needs hand surgery on Helm
secrets. **Only if the run printed `STOP` after the cap** (controller wedged):
`kubectl rollout restart deploy/helm-controller -n flux-system`, then
`helm history n8n -n home-automation`; if the newest revision is
`pending-upgrade`, delete exactly that revision's secret
(`kubectl delete secret sh.helm.release.v1.n8n.v<N> -n home-automation`) so the
previous `deployed` revision (v66 today) is current again, then re-run the block.
Attended operator decision; do not script it.

```bash
# R2 empty the volume of consumers, then POLL until zero pods exist (Multi-Attach guard)
kubectl scale deploy/n8n -n home-automation --replicas=0
for i in $(seq 1 36); do N=$(kubectl get pods -n home-automation -l app.kubernetes.io/name=n8n --no-headers | wc -l); [ "$N" -eq 0 ] && break; sleep 5; done; echo "pods=$N"
```
PASS: `pods=0`. If not 0 after 3 min, STOP and look (a terminating pod holding
the volume); do not start the restore pod. (If Helm had ALREADY rolled back
before R1, a 2.44.5 pod may be running on the migrated DB: R2 removes it; its
writes are discarded by the restore below.)

**Path A - file-level restore from the Mac tar (§2.5 b), preferred (minutes):**

```bash
RB=n8n-restore-$(date +%m%d%H%M)
# GUARD 1 (before the restore pod exists): replicas must be 0 and no n8n pod may exist
REP=$(kubectl get deploy n8n -n home-automation -o jsonpath='{.spec.replicas}'); NP=$(kubectl get pods -n home-automation -l app.kubernetes.io/name=n8n --no-headers | wc -l)
echo "replicas=$REP pods=$NP"; { [ "$REP" = "0" ] && [ "$NP" -eq 0 ]; } || { echo "STOP: not empty - redo R2"; exit 1; }
kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata: {name: $RB, namespace: home-automation, labels: {restore-proof: "true"}}
spec:
  restartPolicy: Never
  enableServiceLinks: false
  securityContext: {runAsUser: 1000, runAsGroup: 1000, fsGroup: 1000, runAsNonRoot: true}
  containers:
    - name: r
      image: n8nio/n8n:2.44.5@sha256:bcb4e4917141f4a5249c8eadf2776d347f4c2ede75adfbbc82064826af9a8ead
      command: ["sh","-c","sleep 1800"]
      volumeMounts: [{name: data, mountPath: /home/node/.n8n}]
  volumes: [{name: data, persistentVolumeClaim: {claimName: n8n-config}}]
EOF
kubectl wait --for=condition=Ready pod/$RB -n home-automation --timeout=180s
# GUARD 2 (immediately before touching the files): still replicas 0, and the restore pod is the ONLY pod on the volume
REP=$(kubectl get deploy n8n -n home-automation -o jsonpath='{.spec.replicas}'); NP=$(kubectl get pods -n home-automation -l app.kubernetes.io/name=n8n --no-headers | wc -l)
echo "replicas=$REP n8n-pods=$NP"; { [ "$REP" = "0" ] && [ "$NP" -eq 0 ]; } || { echo "STOP: a n8n pod exists - do not extract"; exit 1; }
# keep the migrated files for forensics (4.3G free), then lay the pre-upgrade files back
kubectl exec -n home-automation $RB -- sh -c 'T=$(date +%s); mkdir /home/node/.n8n/migrated-$T && mv /home/node/.n8n/database.sqlite* /home/node/.n8n/migrated-$T/'
kubectl exec -i -n home-automation $RB -- tar xf - -C /home/node/.n8n < "$B/n8n.tar"
kubectl exec -n home-automation $RB -- ls -l /home/node/.n8n/database.sqlite /home/node/.n8n/database.sqlite-wal /home/node/.n8n/config
kubectl delete pod/$RB -n home-automation --wait=true --timeout=120s
# R2b the volume must STAY free of n8n pods for 60 s before git/resume (catches a late remediation or stray reconcile)
for i in $(seq 1 12); do N=$(kubectl get pods -n home-automation -l app.kubernetes.io/name=n8n --no-headers | wc -l); [ "$N" -ne 0 ] && { echo "FAIL pods=$N"; break; }; sleep 5; done; echo "stable-empty-check-done N=$N"
```
(`$B` is the `BACKUP_DIR` printed in §2.5.) The restore pod is the only
attacher, and it is fully deleted (`--wait`) before anything scales back up.
PASS: `stable-empty-check-done N=0` with no `FAIL` line. A `FAIL pods=1` means
something is still creating pods (re-run R1/R1b, check `flux get hr`), and the
restore must be redone once it is gone, because a 2.44.5 pod may have written to
the restored files.

**Path B - Longhorn restore**, if the Mac tar fails its integrity check, the
extract errors, or was torn (§2.5 caveat): follow `docs/sops/backup.md` "Restore
from Backup" Case B with the `n8n-config` Backup CR recorded in §2.5(a): restore
to a NEW Longhorn volume name (`n8n-config-r1`), commit a PV/PVC pair named for it
(speaking name, `volumeHandle` == name), keep the old PV/Longhorn volume until
V5/V6 pass, then remove it in a later commit. Never delete `n8n-config` first
(a same-name restore leaves the backup store as the only copy). Attended operator
action; the HelmRelease stays suspended and the Deployment at 0 throughout.

**R3 land the GitOps revert (while still suspended), then resume, then scale up:**

```bash
git fetch origin main && git merge --ff-only origin/main
git revert --no-edit <sha-of-§3.3>     # image back to 2.44.5; the 40m / 180 widening goes with it
git log -1 --format=%s && git show --stat HEAD   # 'Revert "fix(container): update n8nio/n8n ...', 1 file
git push origin main
flux resume helmrelease n8n -n home-automation
# Helm's 3-way merge keeps the live replicas=0 (the chart value is 1 in both manifests), so scale up explicitly:
kubectl rollout status deploy/n8n -n home-automation --timeout=300s    # 0 desired: returns at once
kubectl scale deploy/n8n -n home-automation --replicas=1
kubectl rollout status deploy/n8n -n home-automation --timeout=600s
flux get helmreleases -n home-automation n8n
```
(`flux resume` triggers the reconcile; an image change on a Deployment at 0
replicas is harmless. Git already says `replicaCount: 1`, so no extra commit is
needed; the explicit scale only undoes the R2 kubectl scale.)

Confirm the cluster is back:
- V1 prints `n8nio/n8n:2.44.5`; V2 shows imageID `sha256:bcb4e4917141f4a5249c8eadf2776d347f4c2ede75adfbbc82064826af9a8ead`.
- V3 prints `2.44.5` / `v26.10.0`; V4 `200`/`200`, `setup= False`, `login-unauth=401`.
- V5 equals §2.3 (15 / `3124227881 136`) and V6's query reads `302` / `AddTimeoutSecondsToScheduler1791542683581`.
- Leave PR #476 closed. Renovate re-proposes the next stable.

**Is a Helm rollback onto the restored database acceptable?** Yes. Once the DB
is restored to its pre-upgrade state (302 migrations), 2.44.5 is exactly what
wrote it, so Helm rolling the chart/image back to 2.44.5 (by its own remediation
before R1, or by the R3 revert) is consistent. The only illegal combination is
2.44.5 against a MIGRATED database, which the R1/R1b/R2 ordering exists to prevent.

**There is no "keep 2.46.6 after a late kill" branch.** A pod killed or timed out
during migration may leave a half-applied schema, and from outside you cannot
tell until it boots; the only safe states are "migrated and verified by V6 on a
live healthy pod" or "restored". If the pod is alive and healthy, V1-V6 decide;
if it was killed at any point, restore.

## 6) Interference notes

### 6.1 Windows and ordering
- `capability_change: true` + `rollback_class: backup-restore` => derived
  execution class is human-gated (no SD-10 pre-approval); operator GO required,
  expected to be quick. Prefer an **attended** slot; est. 60 min needs a window
  with >= 60 min schedulable (sat-attended budget is 70, nightly 70). Keep it
  out of `sun-attended:2026-11-15` (longhorn-1.13.0), `sun-attended:2026-11-22`
  (talos-linux-1.14.5), `sat-attended:2026-11-28` (helm-drift-detection),
  `sun-attended:2026-12-13` (flux-oci-chart-sources). `sat-attended:2026-11-14`
  is already at 70 min (open-webui-0.13.0 + python-fleet-3.15.2-alpine).
- `window: sun-attended:2026-12-06` (60 of 180 schedulable minutes; scheduler
  tested by the reviewer; second choice `sun-attended:2026-11-29`). The old slot
  `nightly:2026-11-05` is missed and belongs to the superseded plan; it does not
  transfer. This plan reboots nothing; Sunday is chosen because the attended
  operator must do V9 and may need rollback Path B.
- The Step 0 safe-update batch runs first in every window; it cannot move this
  image (denied above patch), but a same-night `kube-prometheus-stack` bump would
  change the instrument V7 reads: none exists as a plan today. If one is
  written, add it to `conflicts_with` on BOTH sides.

### 6.2 Shared surfaces
- Longhorn: the rehearsal creates and deletes ONE 1-replica scratch volume; a
  longhorn engine/manager roll the same night would race it (hence
  `longhorn-1.13.0` in conflicts_with). The all-volumes backup job in §2.5, if
  needed, loads Longhorn and the NAS for several minutes.
- Public edge: `envoy-external` serves 5xx/404 for the n8n host for the whole
  Recreate + migration (est. 2-5 min normally; at most the single 40 m Helm upgrade deadline on a failure, since `retries: 0` removes any rollback leg). No
  steady webhook client exists (§1.2); fire-and-forget senders would lose that
  window.
- No shared postgres: n8n is SQLite, so no `postgresql-*`/pg plan conflicts.

### 6.3 Repo corrections found while planning (reported, not fixed here)
1. (Fixed in the working tree, uncommitted: the stale `nightly:2026-11-05
   (n8n-fleet, low;` fallback was removed from `grafana-14.1.0.md`.)
2. `flux-oci-chart-sources` and `helm-drift-detection` do not name any n8n plan
   in their `conflicts_with`, so the conflict is declared on one side only.
3. `docs/sops/auto-update.md` / `coverage.py` dispatch the **newest** tag while
   `stable` can be several minors behind `beta` (2.47.2 today): correct this time,
   but the old plan's retarget history (2.45.3 beta -> 2.44.6 -> 2.46.6) shows
   the dispatch target must always be re-derived from the npm `stable` dist-tag
   (§2.1), never copied from the previous plan.
4. **Operator decision, not changed fleet-wide:** `upgrade.remediation.retries: 3`
   on stateful apps with forward-only migrations can auto-roll the image back
   over a migrated DB. This plan sets `retries: 0` (and `cleanupOnFail: false`)
   for n8n for this window only, restoring them in §3.5 / the revert. Whether
   stateful HelmReleases should drop automatic remediation or carry an explicit
   `timeout` permanently is a policy call.
