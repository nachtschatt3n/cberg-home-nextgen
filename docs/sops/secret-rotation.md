# SOP: Secret Rotation — rotate the value, then roll EVERY consumer

> Description: How to rotate a Kubernetes Secret that one or more running workloads consume, so that no consumer keeps serving the old value behind a green HelmRelease. Covers consumer enumeration, Stakater Reloader, Flux `postBuild` substitution, and in-pod verification.
> Version: `2026.09.25`
> Last Updated: `2026-09-25`
> Owner: `Platform`

---

## 1) Description

A Secret rewrite does **not** reach a running pod. Environment variables built
from `secretKeyRef` / `envFrom` are captured once, when the container starts,
and nothing in Kubernetes re-reads them. So "rotate the credential in SOPS,
push, HelmRelease Ready=True" leaves every consumer that was not restarted
*after* the Secret landed still holding the deleted value — and failing
silently, because nothing about that state is visible from the manifests.

This SOP exists because that exact failure shipped on 2026-09-14/15 (`bc4a2fbf`,
finding `F-c04cc353`): the shared Paperless API token was re-minted
(`2165b484`), the `mcpo` pod was rollout-restarted 2.5 minutes *before* Flux
rewrote `Secret ai/mcpo-api-key`, the pod template did not change, so nothing
rolled it again and it kept the dead token in `PAPERLESS_API_KEY`. The
HelmRelease was green throughout. It surfaced only as `Unauthorized` lines in
paperless-ngx.

- Scope: every Secret consumed by a Deployment / StatefulSet / DaemonSet /
  CronJob under `kubernetes/apps/`, including Secrets produced by Flux
  `postBuild.substituteFrom` (`cluster-secrets`) and Secrets a Helm chart
  reads through `existingSecret`.
- Prerequisites: SOPS age key on this machine, `kubectl`, `flux`, `sops`
  (mise), the pre-commit hooks (`docs/sops/pre-commit-secret-scan.md`).
- Out of scope: rotating the SOPS **age key** itself
  (`docs/sops/sops-encryption.md`); rotating a **database** password stored in
  the datastore (`docs/sops/bundled-datastore-exit.md` §10 — the DB and every
  client must move together, this SOP only covers the client roll);
  Authentik-managed credentials (`docs/sops/authentik.md`).

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Reload mechanism | Stakater Reloader, chart `2.2.16`, image `ghcr.io/stakater/reloader:v1.4.21` (`kubernetes/apps/kube-system/reloader/app/helmrelease.yaml`, args `--log-level=info`, defaults otherwise) |
| Where annotations go | on the **pod template** (`controllers.<name>.pod.annotations` in app-template 5.x; `spec.template.metadata.annotations` in a plain Deployment) — verified working here, see §3 |
| Substituted Secrets | `kubernetes/flux/components/common/cluster-secrets.sops.yaml` → `${PAPERLESS_API_KEY}`, `${MCPO_API_KEY}`, `${GITHUB_TOKEN}`, … rendered into other Secrets at Kustomization build time |
| Substitution latency | the consuming Kustomization's `interval` (30m for app Kustomizations, e.g. `kubernetes/apps/ai/mcpo/ks.yaml`) unless you `flux reconcile` it |
| Source of truth for "who consumes X" | `grep -rn "name: <secret>" kubernetes/apps` **plus** the live check in §4 step 1 — the manifest grep misses chart-templated references |
| Verification | hash of the value **inside the pod** vs hash of the live Secret — never "the file in git has the new value" |

---

## 3) Blueprints

**Reloader annotation shapes in this repo** (all render on the pod template, and
Reloader v1.4.21 acts on them — measured 2026-09-22 from its own log:
`Changes detected in 'mcpo-config' of type 'CONFIGMAP' in namespace 'ai';
updated 'mcpo' of type 'Deployment'` on a Deployment whose *metadata* carries
no reloader annotation at all, only its pod template does):

```yaml
# app-template 5.x (mcpo, openclaw, affine, immich, sure-postgres …)
controllers:
  <name>:
    pod:
      annotations:
        secret.reloader.stakater.com/reload: <secret-name>           # named Secret(s), comma-separated
        configmap.reloader.stakater.com/reload: <cm-a>,<cm-b>        # named ConfigMap(s)
        # or, for everything the workload references (env, envFrom, volumes):
        reloader.stakater.com/auto: "true"
```

```yaml
# plain Deployment (edot-collector, whiteboard-proxy, paperless validator)
spec:
  template:
    metadata:
      annotations:
        reloader.stakater.com/auto: "true"
```

Reloader's action is a pod-template patch (an env var named
`STAKATER_<OBJECT>_<KIND>` carrying a hash) — that is why a rolled workload
shows `STAKATER_OPENCLAW_SECRET_SECRET` / `STAKATER_MCPO_CONFIG_CONFIGMAP` in
its container env. **The marker is proof the roll happened; its absence after a
rotation is proof it did not.**

**Shared Secrets — the ones where "roll every consumer" means more than one
workload.** Measured 2026-09-22 by scanning every non-SOPS manifest under
`kubernetes/apps/` for `secretKeyRef` / `secretRef` / `secretName` /
`existingSecret` and keeping names referenced from more than one file
(`sops-age` and `ghcr-secret` excluded — Flux/registry plumbing, not app
credentials). The third column is whether **that file** carries a reloader
annotation; `NONE` means the consumer must be rolled by hand.

| Secret | Consumer manifest (kind) | Reloader in that file |
|---|---|---|
| `media-manager-tokens` | `media/library-tools/app/{episode-sidecar,per-item-refresh,plex-fs-classifier,rescan,sidecar}-cronjob.yaml` (5 CronJobs) | NONE — CronJob pods read the Secret at each Job start (§4 note) |
| `authentik-secret` | `kube-system/authentik/app/helmrelease.yaml` | `auto` + named |
| `authentik-secret` | `kube-system/authentik/app/pg-deployment.yaml`, `cronjob-channels-cleanup.yaml`, `cronjob-db-probe.yaml` | NONE |
| `paperless-ngx-secret` | `office/paperless-ngx/app/helmrelease.yaml`, `db-deployment.yaml`, `redis-deployment.yaml` | NONE (all three) |
| `elasticsearch-es-elastic-user` | `monitoring/edot-collector/app/deployment.yaml` | `auto` |
| `elasticsearch-es-elastic-user` | `monitoring/elasticsearch/app/obs-recovery-cronjob.yaml`, `otel-ilm-job.yaml` | NONE |
| `tube-archivist-secrets` | `download/tube-archivist/app/helmrelease.yaml`, `elasticsearch-helmrelease.yaml`, `metadata-sync-cronjob.yaml` | NONE |
| `postgresql` | `databases/postgresql/app/deployment.yaml`, `oc8-db/app/init-job.yaml`, `sweep-history/app/init-job.yaml` | NONE |
| `wazuh-certs`, `wazuh-secret` | `security/wazuh/app/wazuh-{manager,indexer}-statefulset.yaml`, `wazuh-dashboard-deployment.yaml` | NONE |
| `affine-secret` | `office/affine/app/helmrelease.yaml` / `postgres-helmrelease.yaml` | `auto` / named |
| `immich-secret` | `media/immich/app/helmrelease.yaml` / `postgres-helmrelease.yaml` | `auto` / named |
| `sure-secret` | `office/sure/app/helmrelease.yaml` / `postgres-helmrelease.yaml` | NONE / named |
| `mealie-secret` | `office/mealie/app/helmrelease.yaml` / `pg-deployment.yaml` | `auto` / NONE |
| `nextcloud-config` | `office/nextcloud/app/helmrelease.yaml` / `whiteboard-proxy.yaml` | `auto` / `auto` |
| `openclaw-secret` | `ai/openclaw/app/helmrelease.yaml` / `openclaw-probe.yaml` (CronJob) | named / NONE |
| `teslamate-secret`, `penpot-secret`, `paperclip-secret`, `absenty-secrets`, `adguard-home-credentials`, `superset-secrets`, `sweep-history`, `elasticsearch-es-http-certs-public` | two files each — see the scan | NONE |

Re-run the scan rather than trusting this table when it matters; it is a
snapshot.

**The other kind of "shared": one credential in several Secrets.** The
Paperless API token lives in **four** places (`2165b484`):
`openclaw-secret.PAPERLESS_TOKEN`, `arag-web`'s `secret.sops.yaml`
`PAPERLESS_API_KEY`, `cluster-secrets.PAPERLESS_API_KEY`, and — rendered from
that last one by Flux substitution — `mcpo-api-key.PAPERLESS_API_KEY`. A grep
for the Secret *name* finds none of that; grep for the **key name** and the
`${VAR}` form as well.

**A literal `$` in a Secret value must be written `$$`.** Every app
Kustomization is patched with `postBuild.substituteFrom` (`cluster-settings`,
`cluster-secrets`; see `kubernetes/flux/cluster/ks.yaml`). kustomize-controller
runs that substitution on the **decrypted** Secret, so any `$` in the value can
be rewritten before the Secret reaches the cluster. The values this bites are
password hashes: an argon2 PHC string (`$argon2id$v=19$m=…,t=…,p=…$<salt>$<hash>`)
or a bcrypt hash (`$2b$12$…`). Measured in `79d2d504` (vaultwarden
`ADMIN_TOKEN`) with `flux build` on a throwaway object, and live on
2026-09-25 in the running pod:

| Written in the SOPS file | Arrives in the pod as |
|---|---|
| `$$argon2id$$v=19$$…` | `$argon2id$v=19$…` (correct; the live vaultwarden value begins `$argon2id$v=19`) |
| `${NAME}` | the value of `NAME` from the cluster vars. If `NAME` is undefined, the whole Kustomization **fails** in strict mode (kustomize-controller ≥ v1.9, see `docs/sops/flux-upgrade.md`), which blocks every object in it |
| bare `$name` | left alone in the `79d2d504` test. Do not rely on this: the form is correct only by accident of which character follows the `$` |

Rules:

- Escape **every** `$` in the value as `$$`, not only the ones that look like
  `${`. That is the only form whose result does not depend on what follows
  the `$`, and it is what vaultwarden's Secret uses.
- A hash is invalid even when a single `$` is wrong, and the app usually does
  not say so. It either rejects the correct password or treats the value as
  plain text. Verify the prefix in the pod (§6 Test 4), not in git.
- Where a whole object must not be substituted, the per-object opt-out
  annotation `kustomize.toolkit.fluxcd.io/substitute: disabled` is already used
  in this repo (mosquitto, unpoller dashboards). Escaping is preferred for a
  single Secret value, because the opt-out also disables every intended
  `${VAR}` in that object.

---

## 4) Operational Instructions

1. **Enumerate consumers BEFORE touching the value.** Two passes, because
   the manifest grep misses chart-templated references and the live grep
   misses CronJobs that are not running:

   ```bash
   S=<secret-name>; NS=<namespace>
   # manifests: direct references
   grep -rn "name: $S" kubernetes/apps | grep -v "\.sops\.yaml"
   # manifests: the same credential under another key / via substitution
   grep -rn "<KEY_NAME>\|\${<KEY_NAME>}" kubernetes/apps kubernetes/flux | grep -v "ENC\["
   # live: every pod template in the namespace that mounts or envs the Secret
   kubectl -n $NS get deploy,sts,ds,cronjob -o json | /usr/bin/python3 -c "
   import sys,json
   for i in json.load(sys.stdin)['items']:
       s=json.dumps(i['spec'])
       if '\"$S\"' in s: print(i['kind'], i['metadata']['name'])"
   ```

   Write the list down. Every entry needs a tick in step 6.

2. **Rotate at the source first** where the credential is issued by an app
   (Paperless token, API keys): mint the new one, prove it works with one
   direct call, and only then retire the old one. Rotating the Secret before
   the source accepts the new value breaks every consumer at once.

3. **Change every SOPS location in one commit** (`sops <file>.sops.yaml` in the
   repo path, never from `/tmp` — `docs/sops/sops-encryption.md`). Use
   `git commit --only <paths>` (shared worktree). Push.

4. **Land the Secret, and prove it landed.** For a directly-declared Secret the
   app Kustomization applies it on its next reconcile; for a
   substitution-fed Secret (`cluster-secrets` → `mcpo-api-key`) the value
   only changes when the *consuming* Kustomization re-renders — up to its
   30-minute interval unless forced:

   ```bash
   flux reconcile kustomization <app> -n <ns> --with-source
   # the live object's managedFields time must be AFTER your push
   kubectl -n $NS get secret $S -o json --show-managed-fields \
     | /usr/bin/python3 -c "import sys,json;[print(m['manager'],m.get('time')) for m in json.load(sys.stdin)['metadata']['managedFields']]"
   ```

   This ordering is the whole `bc4a2fbf` lesson: the pod was restarted
   between the push and this event, so the restart picked up the OLD Secret.

5. **Roll the consumers — AFTER step 4, never before.**
   - Reloader-annotated workloads roll themselves. Confirm from its log, not
     from the annotation:
     ```bash
     kubectl -n kube-system logs deploy/reloader --since=30m | grep "'$S'"
     # expect: Changes detected in '<S>' of type 'SECRET' in namespace '<ns>'; updated '<workload>' ...
     ```
   - Everything in your step-1 list without a reloader line: roll by hand.
     ```bash
     kubectl -n $NS rollout restart deploy/<name>     # or sts/ds
     kubectl -n $NS rollout status  deploy/<name> --timeout=300s
     ```
   - CronJobs need no roll: each Job creates fresh pods that read the Secret
     at creation. A Job **already running** keeps the old value until it ends.
   - Volume-mounted Secrets (files, not env) are refreshed by the kubelet on
     its sync period **unless mounted with `subPath`**, which never updates.
     This is Kubernetes' documented behaviour; it was not exercised in this
     repo's incident and is stated here as a caution, not a measurement.

6. **Verify inside the pod, against the live Secret** — for EVERY consumer on
   the list. Compare hashes so nothing is printed:

   ```bash
   # value the process actually has
   kubectl -n $NS exec deploy/<name> -c <container> -- sh -c 'printf %s "$<ENV_VAR>" | sha256sum | cut -c1-8'
   # value the cluster holds now
   kubectl -n $NS get secret $S -o jsonpath='{.data.<KEY>}' | base64 -d | shasum -a 256 | cut -c1-8
   ```

   They must match. `bc4a2fbf` was found exactly this way: pod `4697b40b` vs
   Secret `07ffd6f7`.

7. **Prove end-to-end** with one real call per consumer (the paperless canary
   in `docs/sops/paperless.md` §6a, an openclaw skill run, …). A matching
   hash says the pod has the new value; only a 200 says the value is right.

8. **Close the gap for next time.** If a consumer in step 5 had to be rolled by
   hand, add the reloader annotation in the same change set so the next
   rotation does not depend on someone remembering this SOP. That is what
   `bc4a2fbf` did for `mcpo`.

---

## 5) Examples

### Example A: shared API token, four consumers (`2165b484` + `bc4a2fbf`, 2026-09-14/15)

```bash
# 1. consumers: openclaw (openclaw-secret), arag-web (its secret.sops.yaml),
#    cluster-secrets (substituted into mcpo-api-key)
grep -rn "PAPERLESS_TOKEN\|PAPERLESS_API_KEY" kubernetes/apps kubernetes/flux | grep -v "ENC\["
# 2. mint the token in Paperless, prove it:  curl -H "Authorization: Token <new>" https://<paperless-host>/api/documents/?page_size=1  -> 200
# 3. three SOPS edits, one commit, push
# 4. force the substitution consumers to re-render, confirm the Secret changed
flux reconcile kustomization mcpo -n ai --with-source
# 5. openclaw: Reloader (named annotation) -> check its log; mcpo: had NO annotation on 09-14 -> rollout restart
# 6. hash compare per pod; 7. one paperless call from each consumer
```

### Example B: a Secret consumed by a Deployment AND a CronJob (`openclaw-secret`)

The Deployment carries `secret.reloader.stakater.com/reload: openclaw-secret`
and rolls itself; `openclaw-probe.yaml` is a CronJob with no annotation and
needs none — its next Job reads the new value. Verify the Deployment with the
hash compare; verify the CronJob by triggering one run
(`kubectl -n ai create job --from=cronjob/<name> <name>-manual`) and reading its
log.

---

## 6) Verification Tests

### Test 1: the live Secret changed after the push

```bash
kubectl -n <ns> get secret <name> -o json --show-managed-fields \
  | /usr/bin/python3 -c "import sys,json;[print(m['manager'],m.get('time')) for m in json.load(sys.stdin)['metadata']['managedFields']]"
```

Expected:
- a `kustomize-controller` (or `helm-controller`) entry with a time later than the push

If failed:
- `flux get kustomizations -A | grep <app>`; for substitution-fed Secrets, `flux reconcile kustomization <app> -n <ns> --with-source` and re-check

### Test 2: every consumer restarted AFTER the Secret changed

```bash
kubectl -n <ns> get pods -o custom-columns=NAME:.metadata.name,STARTED:.status.startTime
```

Expected:
- each consumer pod's `STARTED` is later than the Test 1 time; annotated workloads also show a `STAKATER_*` env var and a Reloader log line

If failed:
- `kubectl rollout restart` that workload; then add the annotation (§4 step 8)

### Test 3: the in-pod value equals the live Secret

```bash
kubectl -n <ns> exec deploy/<name> -- sh -c 'printf %s "$<ENV>" | sha256sum | cut -c1-8'
kubectl -n <ns> get secret <name> -o jsonpath='{.data.<KEY>}' | base64 -d | shasum -a 256 | cut -c1-8
```

Expected:
- identical 8-character prefixes

If failed:
- the pod started before the Secret landed (Test 2) or reads a different Secret/key than you rotated (re-run §4 step 1)

### Test 4: a value containing `$` survived Flux substitution

```bash
# print only the non-secret prefix of a hash (algorithm + version)
kubectl -n <ns> exec deploy/<name> -- sh -c 'printf %s "$<ENV>" | cut -c1-14'
```

Expected:
- `$argon2id$v=19` (argon2) or `$2b$12$` (bcrypt), with single `$` signs

If failed:
- empty or truncated: an unescaped `${…}` was substituted. `$$` in the pod means
  the value bypassed Flux substitution, so remove the doubling. Fix the SOPS
  value (§3 "A literal `$`")

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| `401` / `Unauthorized` from one consumer right after a rotation, HelmRelease green, pod "recently restarted" | the restart happened **before** Flux rewrote the Secret (`bc4a2fbf`) | Test 1 vs Test 2 timestamps; `rollout restart` again; add a reloader annotation |
| Reloader log shows no line for the Secret | the workload carries no annotation for it (`auto` covers only Secrets the workload references; a *named* annotation is needed for Secrets consumed indirectly) | add `secret.reloader.stakater.com/reload: <name>` on the pod template |
| Secret in the cluster still holds the OLD value 20 minutes after the push | it is rendered from `cluster-secrets` by substitution and the consuming Kustomization has not re-reconciled | `flux reconcile kustomization <app> -n <ns> --with-source` |
| Every consumer of a credential broke at once | the credential was retired at the source before the new one was in every Secret (`2165b484` shape) | re-mint, then follow §4 in order |
| After storing a password hash (argon2/bcrypt), the app rejects the correct password or logs that the value is plain text; or the app Kustomization goes `post build failed … variable not set (strict mode)` | literal `$` in the Secret value was not written as `$$`, so Flux postBuild substitution rewrote it (`79d2d504`) | write every `$` as `$$` in the SOPS value; verify with §6 Test 4 |
| A CronJob keeps failing after the rotation | a Job started before the Secret changed is still running, or the CronJob reads a different key | wait for / delete the in-flight Job; re-run §4 step 1 |

```bash
kubectl -n kube-system logs deploy/reloader --since=1h | grep -i "changes detected"
kubectl -n <ns> get pods -o custom-columns=NAME:.metadata.name,STARTED:.status.startTime
```

---

## 8) Diagnose Examples

### Diagnose Example 1: "which pods still hold the old value?"

```bash
S=<secret>; NS=<ns>; KEY=<key>; ENV=<env-var>
NEW=$(kubectl -n $NS get secret $S -o jsonpath="{.data.$KEY}" | base64 -d | shasum -a 256 | cut -c1-8)
for d in $(kubectl -n $NS get deploy -o name); do
  got=$(kubectl -n $NS exec $d -- sh -c "printf %s \"\$$ENV\" | sha256sum | cut -c1-8" 2>/dev/null)
  [ -n "$got" ] && echo "$d pod=$got secret=$NEW $([ "$got" = "$NEW" ] && echo OK || echo STALE)"
done
```

Expected:
- every line `OK`; a `STALE` line names the consumer to roll

If unclear:
- the Deployment may read the value under a different env name — `kubectl -n $NS get deploy <d> -o jsonpath='{.spec.template.spec.containers[*].env[*].name}'`

### Diagnose Example 2: "did Reloader see the change at all?"

```bash
kubectl -n kube-system logs deploy/reloader --since=2h | grep "'<secret>'"
kubectl -n <ns> get deploy <name> -o jsonpath='{.spec.template.metadata.annotations}{"\n"}'
```

Expected:
- a `Changes detected … updated '<name>'` line, and the pod-template annotation naming the Secret

If unclear:
- Reloader only reacts to a Secret whose **data** changed; a re-encryption with identical plaintext produces no event

---

## 9) Health Check

```bash
# consumers without any reloader annotation, for the Secrets in §3's table
for f in $(grep -rl "secretKeyRef\|secretRef\|existingSecret" kubernetes/apps --include=helmrelease.yaml --include=deployment.yaml 2>/dev/null); do
  grep -q "reloader.stakater.com" "$f" || echo "no reloader: $f"
done
# Reloader itself is up
kubectl -n kube-system get deploy reloader
```

Expected:
- Reloader `1/1`; the "no reloader" list is known and deliberate (DB servers that read the password only at initdb are a legitimate entry)

---

## 10) Security Check

```bash
# nothing decrypted left behind
ls /tmp/*secret* 2>/dev/null; git status --short | grep -v "\.sops\.yaml"
# the old credential is dead at the source (expect 401)
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Token <OLD>" https://<source-host>/api/...
```

Expected:
- no plaintext files, no unencrypted Secret manifests staged
- the retired value is rejected by the issuing system
- no consumer still holds it (§6 Test 3 on every consumer)

---

## 11) Rollback Plan

A rotation is rolled back by restoring the previous value in every SOPS
location (`git revert <commit>`), pushing, forcing the consuming
Kustomizations, and **rolling every consumer again** — the same §4 sequence.
If the old credential was already retired at the source, there is nothing to
roll back to: re-mint and go forward.

```bash
git revert <rotation-commit> && git push
flux reconcile kustomization <app> -n <ns> --with-source   # per consumer
kubectl -n <ns> rollout restart deploy/<consumer>           # per un-annotated consumer
```

---

## 12) References

- `bc4a2fbf` — the mcpo reload fix and the RCA of F-c04cc353's driver
- `2165b484` — the four-consumer Paperless token re-mint
- `79d2d504` — vaultwarden `ADMIN_TOKEN` stored as an argon2id hash with every `$` written `$$`
- `kubernetes/apps/kube-system/reloader/app/helmrelease.yaml`
- `kubernetes/flux/components/common/cluster-secrets.sops.yaml` (substitution source)
- `docs/sops/sops-encryption.md`, `docs/sops/pre-commit-secret-scan.md`
- `docs/sops/bundled-datastore-exit.md` §10 (database credentials move with the datastore)

---

## Version History

- `2026.09.25`: Added the `$` → `$$` rule for Secret values (F-95d6d080). This is the lesson from `79d2d504`: Flux postBuild substitution runs on the decrypted Secret and rewrites `$` sequences, so argon2/bcrypt hashes must store every `$` as `$$`. Added §3 block, §6 Test 4 (in-pod prefix check), and a §7 row. `$$` → `$` was verified live in the vaultwarden pod.
- `2026.09.22`: Initial SOP (F-c04cc353). Grounded in the bc4a2fbf incident, the live Reloader (v1.4.21) log, and a 2026-09-22 scan of shared Secrets under kubernetes/apps.
