# SOP: SSO does not disable local auth — finding the bypass path

> Description: How to determine whether an app fronted by Authentik still accepts a local username/password that bypasses SSO entirely, why "we configured OIDC" is not evidence that it does not, and what to assert per app.
> Version: `2026.09.08`
> Last Updated: `2026-09-08`
> Owner: `cberg-home-ops`

---

## 1) Description

Configuring an app for SSO sets the **intended** front door. It very often does
**not** remove the app's own local login path. Where the app keeps serving a
local credential endpoint, a valid local password grants the app's own admin
role while bypassing Authentik completely: no OIDC, no MFA, no Authentik audit
record, and no trace in Authentik's event log.

This SOP exists because that exact misreading caused a real incident. A Superset
admin password sat as a literal in this **public** repository for ~4.7 months
across 28 commits. The reason nobody went looking was a documented belief that
`AUTH_TYPE = AUTH_OAUTH` meant "there is no database-password path". It does not.
Flask-AppBuilder's `db` provider does not gate on `AUTH_TYPE` — the login
endpoint advertises it unconditionally. Rotated 2026-09-08 (`dad8922c`); the
false statement corrected in `6f326139`.

- Scope: every app in this cluster fronted by Authentik, by either integration mode.
- Prerequisites: `kubectl`, cluster access, ability to port-forward a Service.
- Out of scope: Authentik's own admin auth; SOPS mechanics (`docs/sops/sops-encryption.md`);
  what to do once a secret is known-leaked (`docs/sops/vulnerability-disclosure.md`).

---

## 2) Overview

**The distinction that decides everything is the integration mode**, not whether
"SSO is set up".

| Mode | How it is wired | Who serves the login page | Local-auth risk |
|---|---|---|---|
| **forward-auth** | HTTPRoute → Authentik outpost → app; app sees a pre-authenticated request | **Authentik**, at the edge | **Gated.** The app's local form is unreachable without passing Authentik first. Still keep the local password strong and in SOPS, but it is not a bypass. |
| **in-app OIDC/OAuth** | App has its own user model and OIDC client config | **The app itself** | **NOT gated.** The app serves its own endpoints, including any local provider. A local password is a direct bypass of Authentik. |

| Setting | Value |
|---|---|
| Authentik blueprints | `kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml` |
| Integration reference | `docs/sops/authentik.md` |
| Routing model | HTTPRoute → Gateway `envoy-internal` (LAN) / `envoy-external` (internet), ns `network` |
| Apps with in-app OIDC (verified 2026-09-08) | `ai/librechat`, `ai/openclaw`, `databases/superset`, `monitoring/headlamp`, `office/mealie`, `office/sure`, `security/falco` |
| Of those, internet-exposed | `ai/librechat`, `office/mealie` — highest priority |
| Everything else | forward-auth (e.g. Grafana, Longhorn, Frigate, phpMyAdmin) |

**Rule:** for any app in the in-app-OIDC row, "SSO is configured" tells you
nothing about local auth. You must check the app's own auth settings.

---

## 3) Blueprints

N/A — this SOP asserts a property of app configuration; it owns no blueprint of
its own. The relevant declarative sources are each app's HelmRelease
(`configOverrides` / `grafana.ini` / env) and its SOPS Secret.

Anti-pattern this SOP forbids, verbatim from the Superset HelmRelease:

```yaml
    # Do NOT reintroduce a literal password here to "make it declarative".
    init:
      createAdmin: false
```

A chart's `createAdmin`-style option re-asserts a local admin on **every**
upgrade, from a value that must then live somewhere. Set it `false` and let the
credential live only in SOPS.

---

## 4) Operational Instructions

1. **Classify the app** — forward-auth or in-app OIDC. Read its `httproute.yaml`:
   a route whose backend is `ak-outpost-*` is forward-auth; a route pointing
   straight at the app Service, with OIDC in the HelmRelease, is in-app.
2. **For in-app OIDC apps, enumerate the local providers the app still accepts**
   (§5). Do this against the running app, not the config — the config is what
   misled us before.
3. **Decide per app**: disable the local path outright, or accept it and treat
   the local credential as a first-class secret (SOPS only, strong, rotatable).
4. **Turn off any chart option that re-creates a local admin** on upgrade.
5. **Record the outcome in `docs/applications.md`** on the app's row — the auth
   model, and any rollback caveat (see §11).
6. Commit and push; Flux reconciles.

```bash
git commit --only kubernetes/apps/<ns>/<app>/app/helmrelease.yaml -F msg.txt
git show --stat HEAD   # shared worktree: confirm no foreign hunk rode along
git push
```

---

## 5) Examples

### Example A: enumerate accepted login providers — credential-free

This is the check that would have caught the incident. It uses **no credential**:
an unknown provider is rejected by input validation, and the error lists exactly
what the app does accept.

```bash
mise exec -- kubectl -n databases port-forward svc/superset 18088:8088 >/dev/null 2>&1 &
sleep 5
curl -s -X POST http://localhost:18088/api/v1/security/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"probe","password":"probe","provider":"notaprovider","refresh":false}'
kill %1
```

Observed 2026-09-08:

```json
{"message":{"provider":["Must be one of: db, ldap."]}}
```

`db` is listed **despite** `AUTH_TYPE = AUTH_OAUTH`. That is the bypass path.

### Example B: interpreting a 401 correctly

```bash
# nonexistent user, provider=db
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost:18088/api/v1/security/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"no-such-user","password":"x","provider":"db","refresh":false}'
# -> 401
```

**A 401 means "wrong credential", not "no credential path".** Reading 401 as a
closed door is the precise error this SOP exists to prevent. The door is closed
only when the provider is absent from the validation list in Example A, or when
no local user holds a usable password.

### Example C: the forward-auth contrast (Grafana)

Grafana has a local admin (`grafana-admin-secret`) and no in-app OIDC. That is
**fine**, because its HTTPRoute sends traffic through the Authentik outpost
first — the local form is never exposed. Verify the gate is actually in place
rather than assuming it:

```bash
mise exec -- kubectl -n monitoring get httproute grafana \
  -o jsonpath='{range .spec.rules[*].backendRefs[*]}{.name}{"\n"}{end}'
```

If a rule points straight at the Grafana Service with no outpost rule alongside
it, the local login form is directly reachable and this app has silently moved
into the in-app row.

---

## 6) Verification Tests

### Test 1: the local provider is gone, or knowingly accepted

```bash
mise exec -- kubectl -n <ns> port-forward svc/<app> 18088:<port> >/dev/null 2>&1 &
sleep 5
curl -s -X POST http://localhost:18088/<login-endpoint> \
  -H 'Content-Type: application/json' \
  -d '{"username":"probe","password":"probe","provider":"notaprovider"}'
kill %1
```

Expected:
- The returned provider list contains **only** the providers you intend to accept.

If failed:
- An unexpected provider is listed → §7 row 1. Do not conclude anything from a 401.

### Test 2: no chart option re-creates a local admin

```bash
mise exec -- kubectl -n <ns> get helmrelease <app> \
  -o jsonpath='{.spec.values}' | python3 -m json.tool | grep -iE 'createAdmin|adminUser|admin_password'
```

Expected:
- `createAdmin: false`, or no such key at all.

If failed:
- Set it false. Otherwise the next upgrade re-asserts the local admin from a
  value that has to be stored somewhere — which is how the literal appeared.

### Test 3: no credential literal in the manifest

```bash
git -C . grep -nE '(password|secret|token)\s*[:=]\s*["'"'"']?[A-Za-z0-9._@!%-]{8,}' \
  kubernetes/apps/<ns>/<app>/ | grep -v '\.sops\.yaml'
```

Expected:
- No hits outside `*.sops.yaml`.

If failed:
- Treat as a live leak: rotate first, then remove. Removing the literal alone
  does nothing — git history is public and permanent.

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---|---|---|
| Login endpoint lists a provider you thought SSO disabled | The SSO setting selects the *default* auth type; it does not remove other providers | Decide: remove the local user's password, or accept it and manage the credential in SOPS (§4.3) |
| 401 read as "no password path exists" | The exact incident error | Re-run Example A. Only the provider list is evidence |
| Local admin reappears after a chart upgrade | `createAdmin`-style option still true | Test 2 |
| An app moved from forward-auth to in-app OIDC and nobody re-checked | Auth posture changed with the routing change | Re-run §4 classification; update `docs/applications.md` |
| Secret scanner never flagged a repo literal | Pre-commit Layer 1 substring-matches decoded **cluster** Secrets; a value that is not in a cluster Secret, or predates the hook, is not matched | `docs/sops/pre-commit-secret-scan.md`; do not treat a clean scan as proof of absence |

```bash
# Which mode is each Authentik-fronted app in?
mise exec -- kubectl get httproute -A -o json | python3 -c "
import sys,json
for i in json.load(sys.stdin)['items']:
    b=[r.get('name','') for ru in i['spec'].get('rules',[]) for r in ru.get('backendRefs',[])]
    if any('ak-outpost' in x for x in b):
        print('forward-auth', i['metadata']['namespace'], i['metadata']['name'])
"
```

---

## 8) Diagnose Examples

### Diagnose Example 1: "is this SSO-only?" — the full walk

```bash
NS=databases; APP=superset
# 1. routing: does an Authentik outpost sit in front?
mise exec -- kubectl -n $NS get httproute $APP -o jsonpath='{.spec.rules[*].backendRefs[*].name}{"\n"}'
# 2. exposure: LAN-only or internet?
mise exec -- kubectl -n $NS get httproute $APP -o jsonpath='{.spec.parentRefs[*].name}{"\n"}'
# 3. the only authoritative step: ask the app what it accepts (Example A)
```

Read in that order. Step 3 overrides any conclusion drawn from steps 1 and 2 or
from the HelmRelease.

### Diagnose Example 2: a leaked local credential

```bash
# how long was it public, and where?
git log --oneline -S'<no — never paste the value>' -- kubernetes/apps/<ns>/<app>/
```

Do **not** run the above with the real value on a shared machine or paste output
anywhere. Identify the introducing commit by path and date instead:

```bash
git log --oneline --follow -- kubernetes/apps/<ns>/<app>/app/helmrelease.yaml | tail -20
```

Then: rotate first, remove the literal second, and check §11 for the retained
rollback artifacts that still carry the old value.

---

## 9) Health Check

```bash
# every in-app-OIDC app still classified correctly
for a in "ai librechat" "ai openclaw" "databases superset" "monitoring headlamp" \
         "office mealie" "office sure" "security falco"; do
  set -- $a
  echo -n "$1/$2 parents: "
  mise exec -- kubectl -n $1 get httproute $2 -o jsonpath='{.spec.parentRefs[*].name}' 2>/dev/null
  echo
done
```

Expected:
- Each app appears with the Gateway you expect. A move from `envoy-internal` to
  `envoy-external` on an app with a live local provider is an escalation and
  needs its own review.

---

## 10) Security Check

```bash
# 1. no credential literals outside SOPS anywhere in the app tree
git -C . grep -nE '(password|adminPassword|secret_key)\s*:\s*["'"'"']?[A-Za-z0-9._@!%-]{8,}' \
  kubernetes/apps/ | grep -v '\.sops\.yaml'
# 2. no chart re-creates a local admin
git -C . grep -n 'createAdmin: true' kubernetes/apps/
```

Expected:
- Both return nothing.

**Reporting boundary:** if a check here finds a live, unfixed exposure, the
detail belongs on the `sweep_findings` record, referenced from committed files
as `security_ref: F-xxxxxxxx`. Never write a credential value — current or
historical — into any file, commit message, or plan.
See `docs/sops/vulnerability-disclosure.md`.

---

## 11) Rollback Plan

**A credential rotation is not rolled back by rolling back the release.** Older
artifacts keep the pre-rotation value alive:

| Artifact | Why it still matters |
|---|---|
| A retained old datastore (e.g. `superset-pg`, kept as the cutover rollback) | Holds the pre-rotation password hash |
| Helm history Secrets (`sh.helm.release.v1.<app>.v<N>`) | Hold the pre-rotation rendered manifest |
| Any backup taken before the rotation | Same as the datastore |

```bash
# what release revisions exist, and which predate the rotation?
mise exec -- kubectl -n <ns> get secret -l owner=helm,name=<app> \
  --sort-by=.metadata.creationTimestamp \
  -o custom-columns=NAME:.metadata.name,CREATED:.metadata.creationTimestamp
```

**Mandatory pre-condition:** any rollback across a rotation boundary MUST reset
the local admin password (or disable the local user) **as part of the rollback
itself, before the app serves traffic** — not as follow-up work. For a leaked
credential this is not optional: the plaintext was published and cannot be
un-published, so restoring the old hash re-arms a permanently known password.

To roll back this SOP itself: `git revert <commit>`. It documents a check and
changes no cluster state, so reverting it is safe and affects nothing running.
