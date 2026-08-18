# SOP: Flux Image Automation Push Authentication

> Description: Diagnose and remediate `ImageUpdateAutomation` objects that scan, resolve, and run on schedule but never push a commit, because their `sourceRef` GitRepository has no write-capable credential. Anonymous HTTPS read succeeds, so every other Flux signal stays green while image updates silently never happen.
> Version: `2026.08.18` (rev 3)
> Last Updated: `2026-08-18`
> Owner: `cberg-agent / cluster-ops`

---

## 1) Description

`ImageUpdateAutomation` is the only Flux controller that must **write** to git. Every
other controller (source, kustomize, helm, image-reflector) only **reads**. On a public
or read-anonymous HTTPS remote those two capabilities decouple completely:

| Capability | Anonymous HTTPS | Consequence |
|---|---|---|
| clone / fetch | works | `GitRepository` reports `Ready=True` |
| push | **impossible** | `ImageUpdateAutomation` can never commit |

Because the GitRepository is genuinely healthy, nothing in the normal Flux surface
(`flux get sources git`, `flux get kustomizations`, `flux get helmreleases`) reports a
problem. The automation keeps running on its interval, keeps computing the correct new
image tag, and keeps throwing the result away.

Worse, the automation object itself is **green most of the time**: it only reports
`Ready=False` on a reconcile where a new tag actually has to be written, and reports
`Ready=True / "repository up-to-date"` on every other one (both states observed 22
minutes apart on 2026-08-18, see §5 Example B). So the failure is invisible to a
point-in-time Ready check and is only reliably detectable via `lastPushCommit`.

- Scope: `image.toolkit.fluxcd.io` objects in any namespace; the `flux-system`
  `GitRepository` they point at; the `FluxInstance` that generates it.
- Prerequisites: `mise exec -- kubectl`, `mise exec -- flux`, repo write access,
  SOPS age key for the git-auth secret.
- Out of scope: image *scanning* failures (that is an `ImageRepository` /
  registry-credential problem, and it surfaces loudly as `Ready=False`).

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Namespace (automations) | `my-software-development`, `my-software-production` |
| Namespace (source + secret) | `flux-system` |
| Source of truth (automations) | `kubernetes/apps/{namespace}/absenty/app/image-automation.yaml` |
| Source of truth (sync source) | `kubernetes/apps/flux-system/flux-operator/instance/helm-values.yaml` |
| Credential secret | `kubernetes/apps/flux-system/flux-operator/instance/git-auth-secret.sops.yaml` → Secret `flux-system/flux-system-git-auth` |
| Critical dependency | `image-automation-controller` + a write-capable git credential |
| Health assertion | `runbooks/health-check.sh` §20 "Flux image automation" + "Flux sync-source credential" |
| Admission guardrail | `kubernetes/apps/flux-system/flux-guardrails/app/imageupdateautomation-sourceref-policy.yaml` |
| Credential class | see `security_ref: F-13845dda` |

**The tell:** `status.lastAutomationRunTime` advances every interval while
`status.lastPushCommit` stays `null`. An automation that has pushed even once will
have a non-null `lastPushCommit` forever after.

**But `lastPushCommit: null` alone is not a fault.** An automation whose policy tag
already matches what is deployed has simply never had a change to make, and will report
null forever while being perfectly healthy. Both shapes exist in this cluster:

| Automation | `lastPushCommit` | policy tag deployed? | Verdict |
|---|---|---|---|
| `my-software-development/absenty-image-updates` | null (before fix) | **no** | broken — update stuck |
| `my-software-production/absenty-image-updates` | null | yes | healthy — nothing to push, push path merely *unproven* |

### The two detection signals this SOP exists to teach

Both are *classes*, not one-off facts. Neither is visible in any `flux get` table.

**Signal 1 — `lastPushCommit == null`. `Ready=True` is worthless for these objects.**
`ImageUpdateAutomation` reports `Ready=True / "repository up-to-date"` on every reconcile
where the tag has not moved since its last failed attempt, and only flips to `Ready=False`
on the subset of reconciles that actually had to write. Both states were observed on the
same two objects 22 minutes apart with no intervening change (§5 Example B). A
point-in-time readiness check therefore *misses this most of the time*. `lastPushCommit` is
the durable evidence. Generalise it: for any controller whose job is a side effect rather
than a state, assert on the **evidence of the side effect**, never on `Ready`.

**Signal 2 — the silently-pruned field.** A field you set in git that the apiserver drops
because it is not in the CRD's structural schema. There is **no error, no event, no warning**;
Helm reports success, the CR reports `Ready=True`, and `kubeconform` cannot see it because
the offending text is Helm *values*, not a manifest. The only reliable detection is to read
the **live object back** and diff it against what you sent — never trust the manifest. See
§8 Diagnose Example 2 for the four-way comparison (git → rendered ConfigMap → live spec →
CRD schema property list) that localises it in one shot. Anything present in the first two
and absent from the third was pruned.

> Applied to this change: every setting in this SOP is verified by reading the live object
> back (§6 Tests 1, 4, 5), and Test 4 additionally proves the guardrail *denies*, because
> "applied" and "effective" are different claims — a `ValidatingAdmissionPolicy` with no
> binding is 100% inert and equally silent.

So the discriminator is `lastPushCommit == null` **AND** the ImagePolicy's resolved tag
is not deployed in that namespace. Alerting on the null alone would produce a finding
that can never clear — the same anti-pattern this repo removed from the fatal-log
assertion. `runbooks/health-check.sh` implements exactly this pair and reports the
null-but-idle case informationally instead of escalating it.

---

## 3) Blueprints

The automation itself is normal and correct — the defect is never here:

```yaml
# kubernetes/apps/<namespace>/<app>/app/image-automation.yaml (abridged)
apiVersion: image.toolkit.fluxcd.io/v1   # v1 only; v1beta2 is gone since the Flux 2.7 image-API GA
kind: ImageUpdateAutomation
spec:
  interval: 30m
  sourceRef:
    kind: GitRepository
    name: flux-system          # <-- the object that must carry the write credential
    namespace: flux-system
  git:
    checkout: { ref: { branch: main } }
    push:     { branch: main }   # <-- requires WRITE
  update:
    path: ./kubernetes/apps/<namespace>
    strategy: Setters
```

The `flux-system` GitRepository is **not** a file in this repo. It is generated by the
flux-operator from the `FluxInstance`, whose values live in:

```yaml
# kubernetes/apps/flux-system/flux-operator/instance/helm-values.yaml
instance:
  sync:
    kind: GitRepository
    url: "<REPO_URL>"
    ref: "refs/heads/main"
    path: kubernetes/flux/cluster
    pullSecret: flux-system-git-auth   # <-- CORRECT KEY. See the trap below.
```

### The pruning trap (root cause of the 2026-08-18 incident)

`FluxInstance.spec.sync` is a **structural** OpenAPI schema whose only credential field
is `pullSecret` (a plain string):

```
sync properties: [interval, kind, name, path, provider, pullSecret, ref, url]
```

The repo declared the *GitRepository*-style form instead:

```yaml
    secretRef:
      name: flux-system-git-auth    # WRONG for FluxInstance.spec.sync
```

`secretRef` is not in the schema, so the apiserver **prunes it silently** — no
validation error, no event, no warning. Helm reports the release healthy, the
FluxInstance reports `Ready=True`, and the generated GitRepository comes out with no
credential at all. `kubeconform` cannot catch this either: the offending text is Helm
*values*, not a Kubernetes manifest.

**Rule:** for `FluxInstance.spec.sync` the key is `pullSecret: <secret-name>`. Only a
`GitRepository` resource itself uses `secretRef: {name: ...}`.

### The confused-deputy consequence of fixing it (2026-08-18, same day)

Restoring the credential turned `image-automation-controller` into a **deputy**. It runs
with `--watch-all-namespaces=true` and *without* `--no-cross-namespace-refs`, so an
`ImageUpdateAutomation` in **any** namespace may name `flux-system/flux-system` as its
`sourceRef` — and the referring namespace never needs permission to *read* the credential
in order to make the controller *push* with it. That was inert while the source carried no
credential. It is not inert now.

**Do not reach for `--no-cross-namespace-refs` / `cluster.multitenant: true`.** Measured on
this cluster 2026-08-18:

| Kind | Total | Cross-namespace `sourceRef` → `flux-system` |
|---|---:|---:|
| `Kustomization` | 135 | **130** |
| `HelmRelease` | 125 | **123** (chart `sourceRef` → `flux-system/<vendor>`) |
| `ImageUpdateAutomation` | 2 | **2** |

Cross-namespace refs are the load-bearing shape of this single-tenant monorepo. The
lockdown flag would break essentially the whole cluster, and it would break the very
automations the push-auth fix restored.

**Do not "fix" it with per-namespace GitRepository + `secretRef` either.** That is the
textbook multi-tenant answer and it is *strictly worse here*: it copies a repo-write PAT
into `my-software-development` / `my-software-production`, namespaces where application
workloads actually run. Today the credential exists **only** in `flux-system`, where no app
workload runs. Cross-namespace referencing is precisely the mechanism that keeps the
credential out of the app namespace — the referrer never reads the secret, the controller
does. Moving the credential closer to the workload trades a *confused-deputy* risk for a
*direct credential-theft* risk, which is a downgrade.

**Bound the severity honestly before you size the fix.** `spec.update.strategy` is an enum
with exactly one legal value, `Setters` (verified against the live CRD). The deputy can
therefore only rewrite values already marked `$imagepolicy` in the repo — cluster-wide that
is **3 sites, all absenty image tags**. An `ImageUpdateAutomation` *cannot* push arbitrary
manifests. The realistic escalation is "steer the absenty image tag to an attacker-chosen
image", not "cluster admin". Real, bounded, worth closing — but do not let a review's
framing of "push to main" drive you into the cluster-breaking fix.

**Reachability, measured:** no principal today can create an `ImageUpdateAutomation` without
already being cluster-admin. There are **zero** `admin`/`edit` RoleBindings in the cluster,
and app-namespace default ServiceAccounts get `no` from `kubectl auth can-i`. This is
therefore *latent* hardening, not a live exploit — but the built-in `edit` ClusterRole
already carries `image.toolkit.fluxcd.io/*: create`, so the day anyone grants a developer
`edit` on `my-software-development`, the hole opens with no further change.

### The guardrail actually applied

A native `ValidatingAdmissionPolicy` (GA since k8s 1.30; this cluster runs 1.36 — no new
controller, no webhook, no new dependency) pins **which namespaces** may make that
cross-namespace reference:

```yaml
# kubernetes/apps/flux-system/flux-guardrails/app/imageupdateautomation-sourceref-policy.yaml (abridged)
kind: ValidatingAdmissionPolicy
spec:
  failurePolicy: Fail            # fail CLOSED; this kind is created ~never
  matchConstraints:
    resourceRules:
      - apiGroups: ["image.toolkit.fluxcd.io"]
        operations: ["CREATE", "UPDATE"]
        resources: ["imageupdateautomations"]   # the only Flux kind that WRITES
  validations:
    - expression: >-
        variables.ref_namespace == '' ||
        variables.ref_namespace == request.namespace ||
        request.namespace in variables.allowed_namespaces
```

Deliberately scoped to `imageupdateautomations` only: the 253 read-only cross-namespace
refs are untouched, so a mistake in this policy **cannot** break Kustomization or HelmRelease
source resolution. Adding a namespace to `allowed_namespaces` is a reviewable git change and
should be read as "granting git-push capability to this namespace".

Residual after the guardrail: the (Setters-bounded) capability is still reachable from the
2 allowlisted namespaces. It is no longer reachable from the other ~40. Two further limits
worth knowing before you rely on it: the allowlist pins the *referrer*, not the *target*, so
an allowlisted namespace may cross-reference any future write-capable source; and
`spec.git.push.branch` / `push.refspec` are unconstrained, so while the commit *content*
stays Setters-bounded, the ref it lands on is not.

> **Before you edit `allowed_namespaces`, know the blast radius.** The two automations are
> not standalone objects — each is owned by its app's own Kustomization
> (`absenty` in `my-software-development` / `my-software-production`). A denial on that one
> resource fails the **entire `absenty` Kustomization**, so a namespace rename, a new
> namespace, or a typo in the allowlist stops the whole application from reconciling, not
> just its image updates. `runbooks/health-check.sh` §20 asserts that every live
> `ImageUpdateAutomation` namespace is present in the allowlist, so this drift is caught
> before Flux hits it — but the coupling is the reason that assertion exists.

### Availability coupling — the cost of the push-auth fix

Before `505fefa4` the GitRepository had no credential and cloned this **public** repo
anonymously. Credential problems could only ever stop *push*. Now that `sync.pullSecret` is
set, source-controller authenticates and **does not fall back to anonymous**. A revoked or
expired token therefore stalls the artifact that all ~136 Kustomizations read from: the
**entire GitOps loop** stops taking new commits, not just image automation.

The live token's expiry characteristics are recorded on `security_ref: F-13845dda`. If it
does not expire, this half of the coupling stays latent until rotation — and rotation to a
fine-grained PAT, which the §10 remediation requires, is exactly what makes it live.
**Rotation and the expiry assertion ship together, or not at all.**

---

## 4) Operational Instructions

> These steps change cluster credentials. Steps 1–2 are read-only. Steps 3–5 are the
> documented remediation and require operator go/no-go because the PAT's scope is
> operator-owned.
>
> **For the 2026-08-18 incident this is now historical** — step 3b was executed in
> `505fefa4`, and the confused-deputy consequence was closed in `c24ffb80` (§3). The
> credential-scope verification called for in §10 has been *performed*; its result and the
> resulting rotation work are tracked on `security_ref: F-13845dda`, not here. Branch
> protection on `main` remains open. Do not re-run steps 3–5 for that incident.

1. **Confirm the shape** (read-only) — §8 Diagnose Example 1.
2. **Confirm which half is missing** (read-only): does the secret exist, and is the
   `sync` field name correct?

   ```bash
   cd /Users/mu/code/cberg-home-nextgen && mise exec -- bash -c '
     kubectl get secret -n flux-system flux-system-git-auth \
       -o jsonpath="{.data}" | python3 -c "import sys,json;print(list(json.load(sys.stdin).keys()))"
     kubectl get fluxinstance -n flux-system flux -o jsonpath="{.spec.sync}" | python3 -m json.tool'
   ```

   - Secret absent → go to step 3a (create credential).
   - Secret present but `spec.sync` has no `pullSecret` → go to step 3b (field-name fix).

3a. **Create the credential** (only if absent). Generate a repo-scoped, **write-capable**
   GitHub credential — either a deploy key with "Allow write access", or a fine-grained
   PAT with `Contents: Read and write` on this repository only. Then, following
   `docs/sops/sops-encryption.md` (encrypt **in** the `kubernetes/` path, never `/tmp`):

   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   mise exec -- sops kubernetes/apps/flux-system/flux-operator/instance/git-auth-secret.sops.yaml
   # stringData:
   #   username: git                 # any non-empty value for a PAT
   #   password: <FINE_GRAINED_PAT>  # never paste this into a shell history or a commit
   ```

3b. **Fix the field name** (the 2026-08-18 case — credential already existed).
   **STATUS: this landed in `505fefa4` on 2026-08-18**; `helm-values.yaml` now carries
   `pullSecret:` and the generated GitRepository has the credential. Kept here as the
   procedure, not as an open action. Step 3a was never needed — the secret pre-existed.

   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   # in kubernetes/apps/flux-system/flux-operator/instance/helm-values.yaml
   #   -   secretRef:
   #   -     name: flux-system-git-auth
   #   +   pullSecret: flux-system-git-auth
   ```

4. **Validate and ship via GitOps** (never `kubectl apply` — the FluxInstance is
   Helm-owned):

   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   # NOTE: `task template:configure` was deleted in d12ca558 (2025-10-05) and no longer
   # exists, despite still being cited in several docs. The live target is `task
   # kubeconform` -- but mind its own caveat (new-deployment-blueprint.md): kubeconform
   # SKIPS every CRD kind, so it can validate nothing and still exit 0. It cannot see a
   # bad FluxInstance value at all; only the live read-back in section 6 can.
   mise exec -- task kubeconform
   mise exec -- kubeconform -summary -exit-on-error -ignore-missing-schemas -strict kubernetes/apps/flux-system/flux-operator
   git add kubernetes/apps/flux-system/flux-operator/instance/helm-values.yaml
   git commit -m "fix(flux): sync credential is pullSecret, not secretRef — silently pruned"
   git pull --rebase && git push
   ```

5. **Verify** — §6 Verification Tests. Expect a `lastPushCommit` within one automation
   interval (30m for the absenty automations).

---

## 5) Examples

### Example A: the healthy shape

```bash
cd /Users/mu/code/cberg-home-nextgen && mise exec -- kubectl get imageupdateautomation -A -o wide
# NAMESPACE  NAME     READY  STATUS                                        LAST RUN
# ns         auto     True   committed and pushed commit 'a1b2c3d' to branch 'main'
```

`lastPushCommit` non-null. Nothing to do.

### Example B: the silent shape (the edge case this SOP exists for)

`Ready` **flaps**, and that is the whole problem. Both states below were observed on
the same two objects within 22 minutes on 2026-08-18, with no intervening change:

```bash
# 16:13 -- a reconcile where a NEW tag had to be written: the failure is visible
# NAMESPACE                NAME                   READY  STATUS
# my-software-development  absenty-image-updates  False  failed to update source:
#                                                        failed to push to remote:
#                                                        authentication required:
#                                                        No anonymous write access.

# 16:35 -- a reconcile where the tag had not moved since the last failed attempt:
# NAMESPACE                NAME                   READY  STATUS
# my-software-development  absenty-image-updates  True   repository up-to-date
```

At 16:35 the object is `Ready=True`, `reason=Succeeded`, message `repository
up-to-date` — indistinguishable from healthy by every ordinary Flux signal — while
`lastPushCommit` is still `null` and not one commit has ever been pushed (duration
and affected workloads: `security_ref: F-4c1f9ab2`). "Up-to-date" here means *the controller compared and found nothing it was able
to write*, not *the cluster is running the latest image*.

**Consequence for any check you write:** a not-Ready assertion alone MISSES this most
of the time, because the object is only red on the subset of reconciles where a new tag
happens to need writing. The durable evidence is `lastPushCommit: null` alongside a
fresh `lastAutomationRunTime`. Never conclude "image automation is fine" from
`Ready=True`, and never conclude it from a green `flux get` table.

---

## 6) Verification Tests

### Test 1: the generated GitRepository now carries a credential

```bash
cd /Users/mu/code/cberg-home-nextgen && mise exec -- \
  kubectl get gitrepository -n flux-system flux-system -o jsonpath='{.spec.secretRef}'
```

Expected:
- `{"name":"flux-system-git-auth"}` (previously empty).

If failed:
- The value never reached the FluxInstance. Re-read §3 "pruning trap" — you almost
  certainly still have `secretRef` where `pullSecret` belongs. Confirm with
  `kubectl get fluxinstance -n flux-system flux -o jsonpath='{.spec.sync}'`.

### Test 2: the automation actually pushes

```bash
cd /Users/mu/code/cberg-home-nextgen && mise exec -- kubectl get imageupdateautomation -A -o json \
  | python3 -c "
import sys, json
for i in json.load(sys.stdin)['items']:
    s = i.get('status', {})
    print(i['metadata']['namespace'], i['metadata']['name'],
          'push=', s.get('lastPushCommit'), 'run=', s.get('lastAutomationRunTime'))"
```

Expected:
- Every automation that has a **pending** update (its ImagePolicy resolved a tag that is
  not deployed) reports a non-null `push=` within one interval.
- An automation with nothing to change legitimately keeps `push= None` forever. That is
  not a failure — its push path is merely *unproven*. To prove it, give it something to
  push (regress the tag by one step and let it push back), or wait for the next real
  image build. `runbooks/health-check.sh` reports this case as
  `NEVER-PUSHED-BUT-IDLE` at info level and does not escalate it.

If failed:
- Non-null secretRef but still no push → the credential is real but **read-only**.
  Re-check the deploy key's "Allow write access" box or the PAT's
  `Contents: Read and write` scope. This is the most common second failure.

### Test 3: the health check now asserts on it

```bash
cd /Users/mu/code/cberg-home-nextgen && grep -n "SILENT-NO-PUSH" runbooks/health-check.sh
```

Expected:
- A match in §20 (GitOps Status). The sweep raises a MAJOR issue whenever an active
  automation has run in the last 24h with `lastPushCommit` null.

### Test 4: the cross-namespace guardrail is live and discriminating

A policy that denies nothing and a policy that denies everything both look "applied".
Prove **both** directions with server dry-runs (non-mutating, nothing persists):

```bash
mise exec -- bash -c '
  kubectl get validatingadmissionpolicy,validatingadmissionpolicybinding \
    flux-imageupdateautomation-sourceref

  mk() { cat <<YAML
apiVersion: image.toolkit.fluxcd.io/v1
kind: ImageUpdateAutomation
metadata: {name: vap-probe, namespace: $1}
spec:
  interval: 30m
  sourceRef: {kind: GitRepository, name: flux-system, namespace: flux-system}
YAML
  }
  echo "--- ALLOWED namespace (must be accepted) ---"
  mk my-software-production   | kubectl apply --dry-run=server -f -
  echo "--- NON-allowlisted namespace (must be DENIED) ---"
  mk default                  | kubectl apply --dry-run=server -f -'
```

Expected:
- allowlisted namespace → `imageupdateautomation.../vap-probe created (server dry run)`
- any other namespace → `admission webhook denied` / `ValidatingAdmissionPolicy ...
  denied request`, quoting the confused-deputy message.

If failed:
- Both accepted → the binding is missing or its `validationActions` is `Audit`/`Warn`
  rather than `Deny`. A `ValidatingAdmissionPolicy` with no `ValidatingAdmissionPolicyBinding`
  is completely inert and reports no error — the same "looks applied, does nothing" class as
  the pruning trap in §3.
- Both denied → the CEL is wrong; `failurePolicy: Fail` converts an evaluation error into a
  blanket deny. Check `.status.typeChecking` on the policy object.

### Test 5: the sync-source credential assertion runs

```bash
cd /Users/mu/code/cberg-home-nextgen && grep -n "Flux sync-source credential" runbooks/health-check.sh
```

Expected:
- A match in §20. It asserts three things: the `secretRef` has not silently vanished again
  (the §3 pruning trap, recurring), the source is not currently failing auth, and the token
  is not expired/expiring (45d minor, 14d major, expired critical).

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| `authentication required: No anonymous write access` | GitRepository has no `secretRef` | §4 step 2, then 3a or 3b |
| GitRepository `Ready=True`, automation never pushes | Same as above — read works, push does not | Same |
| `spec.sync.pullSecret` set but GitRepository still bare | Helm values not rolled | `flux get hr -n flux-system flux-instance`; check it reconciled the new values ConfigMap hash |
| Credential present, push still 403 | PAT/deploy key is read-only | Re-issue with write scope (operator) |
| Automation pushes, but Flux never redeploys | Push branch differs from the sync branch | Compare `git.push.branch` with `FluxInstance.spec.sync.ref` |
| Only signal is a rising generic warning-event count | This exact SOP | §8 Diagnose Example 1 |

```bash
# Quick triage
cd /Users/mu/code/cberg-home-nextgen && mise exec -- bash -c '
  kubectl get imageupdateautomation,imagepolicy,imagerepository -A
  kubectl get gitrepository -n flux-system flux-system -o yaml | grep -A2 secretRef || echo "NO secretRef"
  kubectl logs -n flux-system deploy/image-automation-controller --tail=50 | grep -i "push\|auth"'
```

---

## 8) Diagnose Examples

### Diagnose Example 1: "image updates stopped happening" / unexplained warning events

The symptom often arrives with no name attached — just a warning-event count that never
goes to zero. Walk the three objects in dependency order; the first two will look fine.

```bash
cd /Users/mu/code/cberg-home-nextgen && mise exec -- bash -c '
  echo "--- 1. does it SCAN? (registry creds) ---"
  kubectl get imagerepository -A
  echo "--- 2. does it RESOLVE a tag? ---"
  kubectl get imagepolicy -A
  echo "--- 3. does it PUSH? ---"
  kubectl get imageupdateautomation -A -o wide
  echo "--- 4. the durable tell ---"
  kubectl get imageupdateautomation -A -o json | python3 -c "
import sys, json
for i in json.load(sys.stdin)[\"items\"]:
    s = i.get(\"status\", {}); sp = i.get(\"spec\", {})
    print(i[\"metadata\"][\"namespace\"], i[\"metadata\"][\"name\"])
    print(\"   lastAutomationRunTime:\", s.get(\"lastAutomationRunTime\"))
    print(\"   lastPushCommit:       \", s.get(\"lastPushCommit\"))
    print(\"   sourceRef:            \", sp.get(\"sourceRef\"))"
  echo "--- 5. does the source have a write credential? ---"
  kubectl get gitrepository -A -o json | python3 -c "
import sys, json
for i in json.load(sys.stdin)[\"items\"]:
    sp = i[\"spec\"]
    print(i[\"metadata\"][\"namespace\"], i[\"metadata\"][\"name\"],
          \"scheme=\", sp[\"url\"].split(\":\")[0], \"secretRef=\", sp.get(\"secretRef\"))"'
```

Expected (confirms root cause):
- ImageRepository `Ready=True` — scanning is fine.
- ImagePolicy `Ready=True` with a freshly resolved tag — resolution is fine.
- `lastAutomationRunTime` recent, `lastPushCommit: None`.
- The referenced GitRepository has `scheme= https` and `secretRef= None`.

If unclear:
- If `secretRef` **is** set, the credential exists but lacks write scope — go to Test 2's
  failure hint. If `lastAutomationRunTime` is stale/absent instead, this is not the
  push-auth failure; check the controller is running and the object is not suspended.

### Diagnose Example 2: the value looks right in git but not in the cluster

```bash
cd /Users/mu/code/cberg-home-nextgen && mise exec -- bash -c '
  echo "--- what git says ---"
  grep -A8 "^  sync:" kubernetes/apps/flux-system/flux-operator/instance/helm-values.yaml
  echo "--- what the rendered values ConfigMap says ---"
  CM=$(kubectl get hr -n flux-system flux-instance -o jsonpath="{.spec.valuesFrom[0].name}")
  kubectl get cm -n flux-system "$CM" -o jsonpath="{.data.values\.yaml}" | grep -A8 "sync:"
  echo "--- what the apiserver KEPT ---"
  kubectl get fluxinstance -n flux-system flux -o jsonpath="{.spec.sync}" | python3 -m json.tool
  echo "--- what the schema ALLOWS ---"
  kubectl get crd fluxinstances.fluxcd.controlplane.io -o json | python3 -c "
import sys, json
d = json.load(sys.stdin)
for v in d[\"spec\"][\"versions\"]:
    print(v[\"name\"], list(v[\"schema\"][\"openAPIV3Schema\"][\"properties\"][\"spec\"][\"properties\"][\"sync\"][\"properties\"].keys()))"'
```

Expected:
- git and the ConfigMap both show the credential key; the FluxInstance does **not**.
  The schema list tells you the legal key. Any field you supplied that is absent from
  that list was pruned by the apiserver without comment.

If unclear:
- Diff the whole rendered values against the live spec; the pruning trap generalises to
  every field of `FluxInstance`, not just `sync`.

---

## 9) Health Check

Automated in `runbooks/health-check.sh` §20 (added 2026-08-18). Two assertions now live
there: "Flux image automation" (below) and "Flux sync-source credential" (the availability
coupling — see §3). Manual equivalent for the first:

```bash
cd /Users/mu/code/cberg-home-nextgen && mise exec -- kubectl get imageupdateautomation -A -o json \
  | python3 -c "
import sys, json
from datetime import datetime, timezone, timedelta
now = datetime.now(timezone.utc); bad = 0
for i in json.load(sys.stdin)['items']:
    st, sp = i.get('status', {}), i.get('spec', {})
    if sp.get('suspend'): continue
    run = st.get('lastAutomationRunTime')
    if not run: continue
    if now - datetime.fromisoformat(run.replace('Z','+00:00')) > timedelta(hours=24): continue
    if not st.get('lastPushCommit'):
        bad += 1; print('SILENT-NO-PUSH:', i['metadata']['namespace'], i['metadata']['name'])
print('silent:', bad)"
```

Expected:
- `silent: 0`, and every image-automation object `Ready=True`.

---

## 10) Security Check

```bash
cd /Users/mu/code/cberg-home-nextgen
# the credential is SOPS-encrypted, never plaintext
mise exec -- head -20 kubernetes/apps/flux-system/flux-operator/instance/git-auth-secret.sops.yaml | grep -q "sops:" && echo "ENCRYPTED OK"
# no credential material in the working tree or the commit
git diff --cached | grep -iE "ghp_|github_pat_|-----BEGIN .* PRIVATE KEY-----" && echo "LEAK" || echo "no plaintext credential"
# Flux can still decrypt
mise exec -- kubectl get secret sops-age -n flux-system >/dev/null && echo "age key present"
```

Expected:
- `ENCRYPTED OK`, `no plaintext credential`, `age key present`.
- The credential **should be repo-scoped and write-limited**: a fine-grained PAT with
  `Contents: Read and write` on this repository only, or a per-repo deploy key. A
  classic PAT with account-wide `repo` scope is over-privileged for this job — a
  compromised image-automation controller would inherit write access to every
  repository the token can reach.
- **Measured 2026-08-18: it does not meet this bar.** Detail, blast radius, and rotation
  steps are on `security_ref: F-13845dda` — deliberately not reproduced in this public repo,
  per `docs/sops/vulnerability-disclosure.md`. Rotation is operator-owned (GitHub UI).
- **Cross-namespace push capability is pinned at admission.** See §3 "The guardrail actually
  applied". Any namespace added to that allowlist is being handed git-push capability;
  review it on those terms, not as a routine manifest edit.
- Granting write access to the cluster's git remote widens the blast radius of any
  in-cluster compromise. Prefer a **deploy key** (single repository by construction)
  over a PAT (account-scoped) where GitHub allows it.
- **Say the blast radius plainly: git write access to this repo is equivalent to
  cluster admin.** Flux reconciles `main` continuously, so anyone holding this
  credential can push arbitrary manifests that the cluster then applies. Neither a
  deploy key nor a fine-grained PAT can be scoped to a path — the credential that lets
  Flux bump one image tag lets it rewrite every manifest in the cluster. Require branch
  protection on `main` (block force-push and deletion); a write-enabled deploy key can
  otherwise force-push and delete branches.
- **The deploy-key option requires an SSH remote.** Step 3a's secret template is the
  HTTPS basic-auth (PAT) shape. A deploy key additionally requires changing
  `FluxInstance.spec.sync.url` from `https://` to `ssh://git@github.com/<owner>/<repo>`
  and a secret with `identity` / `identity.pub` / `known_hosts` keys instead of
  `username` / `password`. Following 3a with a deploy key but an https URL produces a
  non-working config with no useful error. Choose one path and change both halves.
- **Expiry is a silent re-break that the "has it ever pushed" assertion cannot catch.**
  Fine-grained PATs expire; classic PATs may; deploy keys do not. When the credential
  expires the automation keeps running, keeps resolving tags, and stops pushing — but
  `lastPushCommit` stays non-null from the pre-expiry pushes, so §9's assertion reads
  healthy straight through the outage. **And since `505fefa4` the damage is no longer
  confined to image automation**: the sync source authenticates and does not fall back to
  anonymous, so expiry stalls every Kustomization in the cluster. This is now covered
  proactively by the "Flux sync-source credential" assertion (§6 Test 5), which queries
  GitHub's `github-authentication-token-expiration` header and warns at 45d / 14d before
  escalating. Record any new expiry date in §2 when rotating.
- **Rotation procedure** (revocation first — a value that reached a public repo cannot be
  recalled from clones): revoke at GitHub → `mise exec -- sops` the new value in-path →
  commit + push → confirm `lastPushCommit` advances on the next pending update.

---

## 11) Rollback Plan

The change is a single GitOps-tracked values edit; revert it the normal way.

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert <sha> && git pull --rebase && git push
```

Rolling back returns the cluster to "image automation never pushes" — degraded but
*safe*: no partial state, nothing to clean up, all other Flux reconciliation unaffected.
If the credential itself must be withdrawn, revoke the PAT/deploy key at GitHub first
(that takes effect immediately), then revert the manifest.

Do **not** roll back by editing the GitRepository or FluxInstance with `kubectl` — both
are Helm/operator-owned and will be overwritten on the next reconcile.

---

## 12) References

- `runbooks/health-check.sh` §20 — the "Flux image automation" assertions
- `runbooks/health-check.md` — health-check procedure
- `docs/sops/flux-upgrade.md` — flux-operator / FluxInstance lifecycle
- `docs/sops/self-built-image-rebuild.md` — what image automation is *supposed* to
  deliver for first-party images
- `docs/sops/sops-encryption.md` — encrypting the git-auth secret in-path
- `kubernetes/apps/flux-system/flux-operator/instance/helm-values.yaml`
- `kubernetes/apps/{my-software-development,my-software-production}/absenty/app/image-automation.yaml`
- Flux docs: image automation requires push access to the `sourceRef` GitRepository

---

## Version History

- `2026.08.18` (rev 3): Closed the confused-deputy exposure that rev 2's fix created.
  Established by cluster-wide inventory that cross-namespace source refs are load-bearing
  (130/135 Kustomizations, 123/125 HelmReleases, 2/2 ImageUpdateAutomations point at
  `flux-system`), so `--no-cross-namespace-refs` / `cluster.multitenant: true` was rejected
  as cluster-breaking, and per-namespace `GitRepository` + `secretRef` was rejected as
  strictly worse (it would move a repo-write PAT into namespaces where app workloads run).
  Applied a narrowly-scoped native `ValidatingAdmissionPolicy` instead, pinning which
  namespaces may cross-reference the write-capable source. Bounded the severity honestly:
  `update.strategy` is a one-value enum (`Setters`), so the deputy can only rewrite the 3
  existing `$imagepolicy` sites, and no non-cluster-admin principal can create the object
  today (zero `admin`/`edit` RoleBindings). Recorded the availability coupling — the sync
  source no longer falls back to anonymous, so credential loss now stalls the whole GitOps
  loop — and added the "Flux sync-source credential" health assertion (vanished-secretRef,
  live auth failure, token expiry at 45d/14d/expired). Resolved rev 2's OPEN scope question
  by probing the live token; it is the over-privileged class, tracked as
  `security_ref: F-13845dda`. Promoted the two detection signals to their own §2 subsection.
  Branch protection on `main` remains OPEN.
- `2026.08.18` (rev 2): Remediation executed in `505fefa4` (field-name fix; no new
  credential was needed). Corrected the §3 blueprint from the retired
  `image.toolkit.fluxcd.io/v1beta2` to `v1` — the live CRD serves v1 only since the
  Flux 2.7 image-API GA. Added the null-but-idle distinction to §2/§6/§9, the SSH
  requirement for the deploy-key path, PAT expiry/rotation guidance, and the plain
  statement that repo write access is cluster-admin-equivalent here. OPEN: verify the
  live token's scope class and add branch protection on `main`.
- `2026.08.18`: Initial version. Written from the 2026-08-18 sweep finding: both
  `absenty-image-updates` automations had `lastPushCommit: null` since creation
  because the `flux-system` GitRepository carried no `secretRef` (duration and
  affected workloads: `security_ref: F-4c1f9ab2`). Root cause
  traced to `FluxInstance.spec.sync` accepting `pullSecret` (string) while the repo
  declared `secretRef` (object), which the apiserver pruned silently. Remediation
  documented, not executed — the PAT scope is operator-owned. Also records the
  observed `Ready` flap (False at 16:13, True/"repository up-to-date" at 16:35, same
  objects, no change in between), which is why the health-check assertion keys on
  `lastPushCommit` rather than on `Ready`.
