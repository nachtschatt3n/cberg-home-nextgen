# SOP: In-App Credential Rotation for Vault-Only Secret Keys

> Description: How to rotate, verify and recover credentials that SOPS holds but that NO workload consumes -- the application's own database is the live copy, so git/SOPS and the app can drift apart silently.
> Version: `2026.09.22`
> Last Updated: `2026-09-22`
> Owner: `cluster-ops-agent` (doc: `doc-agent`)

---

## 1) Description

Most Secret keys in this repository are **projected**: a pod reads them as an
env var or a mounted file, so the value in SOPS is, by construction, the value
the workload runs with. The freshness/liveness check in `runbooks/health-check.sh`
("Shared API Credential Liveness") covers that class by hashing the in-pod
value against the Secret.

A **vault-only** key is different. SOPS holds a credential, the Secret is
created in the cluster, and *nothing mounts it*: the application stores its own
copy (typically a password hash in its metadata database) and authenticates
against THAT. The SOPS copy is a vault entry the operator uses to log in, not
an input the app reads. Consequences:

- An in-app password reset (UI, CLI, `fab reset-password`, a restore from an
  older backup) changes the live copy and leaves SOPS stale. No pod restarts,
  no reconcile fails, no alert fires.
- Rotating the SOPS value alone changes nothing in the app. Flux happily
  applies the new Secret; the app keeps the old hash.
- Neither direction of drift is visible to any GitOps signal. **The only
  assertion that means anything is a real login with the SOPS value.**

This SOP exists because `F-9d938fce` found exactly that gap on Superset:
`superset-secrets.MU_ADM_PASSWORD` lives in SOPS, is consumed by no workload,
and after the 2026-09-08 FAB reset nothing could have told SOPS from the live
DB. The health check now performs the login (see §9); this document is the
procedure around it.

- Scope: every SOPS key with no consuming workload. Known instances are
  enumerated in §2; discovering new ones is §4 step 0.
- Prerequisites: `kubectl` against the cluster, the local age key
  (`SOPS_AGE_KEY_FILE`), `sops`, and -- for the in-app half -- exec access to
  the app's pod or its admin CLI.
- Out of scope: projected keys (covered by the existing freshness check),
  Authentik-managed SSO identities (rotated in Authentik blueprints), and
  keys that the chart's init job consumes on every upgrade (those are
  projected, once).

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Vault (source of truth for the *intended* value) | `kubernetes/apps/<ns>/<app>/app/secret.sops.yaml` (SOPS, age) |
| Live copy (what actually authenticates) | the application's own metadata DB |
| Detector | `runbooks/health-check.sh` section "Superset FAB Credential (vault-only SOPS keys)" -- `superset_fab_probe` / `superset_fab_score` |
| Verdicts | `200` ok · `401` MAJOR "vault-only credential drift" · unreachable/no pod/no key -> recorded as **unmeasured** (never a pass) |
| Rotation order | **SOPS first, then the app, then the probe** -- never the app first |
| Regression test | `runbooks/tests/test-health-check-superset-fab-credential.sh` |

Known vault-only keys (2026-09-22):

| Namespace / Secret | Key | App identity | Why nothing consumes it |
|---|---|---|---|
| `databases/superset-secrets` | `MU_ADM_PASSWORD` | Superset FAB user `mu_adm` (local `db` provider, Admin) | Created in-app; the chart never reads this key |
| `databases/superset-secrets` | `ADMIN_PASSWORD` | Superset FAB user `admin` | `init.createAdmin: false` since `dad8922c`, so the init job no longer (re)asserts it |

Both are probed by the health check. Add a row here **and** a `"user|KEY"`
entry to the probe loop in `health-check.sh` whenever a new vault-only key is
introduced; a key that is only in this table is documented, not measured.

---

## 3) Blueprints

N/A for the credential itself -- there is deliberately no declarative object
that pushes a vault-only value into the app (that would make it projected, and
for Superset it would re-create the "chart re-asserts a local admin on every
upgrade" problem that `init.createAdmin: false` removed).

What IS declarative:

- Source of truth file(s): `kubernetes/apps/databases/superset/app/secret.sops.yaml`
  (encrypted `data`/`stringData` only, per `.sops.yaml`)
- Related manifests: `kubernetes/apps/databases/superset/app/helmrelease.yaml`
  (`init.createAdmin: false`)
- The detector: `runbooks/health-check.sh` -- the probe loop is the registry of
  what is measured:

```bash
# health-check.sh, section "Superset FAB Credential (vault-only SOPS keys)"
for _spec in "mu_adm|MU_ADM_PASSWORD" "admin|ADMIN_PASSWORD"; do
    superset_fab_score "${_spec%%|*}" "${_spec#*|}" \
        "$(superset_fab_probe databases superset-secrets "${_spec#*|}" "${_spec%%|*}")"
done
```

---

## 4) Operational Instructions

### Step 0 -- Prove the key is vault-only (once per key)

A key is vault-only only if **no** workload projects it. "I could not find a
consumer" is not proof; enumerate:

```bash
NS=databases; SECRET=superset-secrets; KEY=MU_ADM_PASSWORD
# env / envFrom / volume references across every workload in the namespace
kubectl get deploy,sts,ds,cronjob,job -n "$NS" -o json | python3 -c "
import sys, json
key, secret = '$KEY', '$SECRET'
for it in json.load(sys.stdin)['items']:
    spec = it['spec'].get('template', it['spec'].get('jobTemplate', {}).get('spec', {}).get('template', {})).get('spec', {})
    hits = []
    for c in spec.get('containers', []) + spec.get('initContainers', []):
        for e in c.get('env', []) or []:
            ref = (e.get('valueFrom') or {}).get('secretKeyRef') or {}
            if ref.get('name') == secret and ref.get('key') == key: hits.append(('env', c['name']))
        for ef in c.get('envFrom', []) or []:
            if (ef.get('secretRef') or {}).get('name') == secret: hits.append(('envFrom(whole secret)', c['name']))
    for v in spec.get('volumes', []) or []:
        if (v.get('secret') or {}).get('secretName') == secret: hits.append(('volume', v['name']))
    if hits: print(it['kind'], it['metadata']['name'], hits)
"
```

`envFrom` of the whole Secret counts as a consumer *only* if the app reads
that variable -- for Superset, `superset-secrets` is env-projected but the
image never reads `MU_ADM_PASSWORD`, which is the case this SOP is for.
Record the proof in the §2 table.

### Step 1 -- Rotate in SOPS FIRST

```bash
cd /Users/mu/code/cberg-home-nextgen
NEW=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')   # strong, never echoed
sops kubernetes/apps/databases/superset/app/secret.sops.yaml              # edit MU_ADM_PASSWORD in $EDITOR
unset NEW
git commit --only kubernetes/apps/databases/superset/app/secret.sops.yaml -m "chore(superset): rotate MU_ADM_PASSWORD"
git show --stat HEAD      # only your file, shared worktree
git push
flux reconcile kustomization superset -n flux-system --with-source   # or wait for the webhook
kubectl get secret -n databases superset-secrets -o jsonpath='{.data.MU_ADM_PASSWORD}' | base64 -d | sha256sum | cut -c1-8   # fingerprint only
```

The order matters: with SOPS rotated first, the health check goes **401 = MAJOR**
until Step 2 lands -- loud, and exactly what you want. Rotating the app first
leaves SOPS wrong with the check green until someone notices by hand.

### Step 2 -- Apply the SOPS value in the app (Superset example)

Read the value from the **live Secret** inside the pod, so the app receives
precisely what the vault holds -- never retype it, never put it on argv:

```bash
POD=$(kubectl get pods -n databases -l app.kubernetes.io/name=superset,app.kubernetes.io/component=web \
      --no-headers | awk '$3=="Running"{print $1; exit}')
kubectl get secret -n databases superset-secrets -o jsonpath='{.data.MU_ADM_PASSWORD}' | base64 -d \
  | kubectl exec -i -n databases "$POD" -c superset -- sh -c 'superset fab reset-password --username mu_adm --password "$(cat)"'
```

(`superset fab reset-password` is Flask-AppBuilder's CLI; `--password` read
from stdin via `$(cat)` inside the pod keeps the value off this machine's argv
and off the pod's process list for longer than the exec.)

### Step 3 -- Verify with the detector, not by eye

Run §6 Test 1. A `200` closes the loop; anything else is §7.

### Step 4 -- Record

Close the finding (if one was open) with the commit:
`python3 runbooks/policy-cli.py finding close <id> --commit <sha>`. Update the
§2 table if the key set changed.

---

## 5) Examples

### Example A: Scheduled rotation of `MU_ADM_PASSWORD`

Steps 1-3 above, in order. Expected timeline: commit -> Flux applies the Secret
(<= 1 min via webhook) -> `fab reset-password` (seconds) -> health-check probe 200.

### Example B: Someone reset the password in the Superset UI (drift, app-first)

Symptom: the sweep raises **MAJOR "Superset vault-only credential drift:
superset-secrets.MU_ADM_PASSWORD is rejected for FAB user mu_adm (401)"**.

Do NOT "fix" it by resetting the app to the old SOPS value -- the person who
reset it had a reason (possibly a compromise). Instead:

1. Find out who/why: `superset` audit log (`Security -> Action Log`) and the
   Authentik audit trail if SSO was involved.
2. Decide the NEW value, then run Step 1 (SOPS) and Step 2 (app) with it, so
   both copies converge on a value that lives in the vault.
3. Step 3 to confirm.

### Example C: Restore from a pre-rotation backup

`docs/applications.md` (superset row) carries the mandatory caveat: the single
surviving `superset-pg-data` backup predates the 2026-09-08 rotation and holds
the OLD hashes for **every** local-db Admin (`admin`, `mu_adm`). After any
restore across that boundary, run Step 2 for EACH key in the §2 table before
Superset serves traffic, then Step 3. Enumerate accounts with
`superset fab list-users` in-pod rather than assuming the table is complete.

---

## 6) Verification Tests

### Test 1: The SOPS value authenticates (the detector itself)

```bash
cd /Users/mu/code/cberg-home-nextgen
python3 - <<'PY'
import re, subprocess
s = open("runbooks/health-check.sh").read()
def grab(n):
    i = s.index(f"{n}() {{"); j = s.index("\n}\n", i) + 3; return s[i:j]
open("/tmp/_fab.sh","w").write(grab("superset_fab_probe"))
PY
mise exec -- bash -c 'source /tmp/_fab.sh; superset_fab_probe databases superset-secrets MU_ADM_PASSWORD mu_adm'; rm -f /tmp/_fab.sh
```

Expected:
- prints `200`

If failed:
- `401` -> drift; §5 Example B. `nopod` / `nosecret` / `unreachable` -> §7.

### Test 2: Wrong-password control (the probe can actually fail)

```bash
POD=$(kubectl get pods -n databases -l app.kubernetes.io/name=superset,app.kubernetes.io/component=web --no-headers | awk '$3=="Running"{print $1; exit}')
printf '%s' "definitely-not-the-password" | kubectl exec -i -n databases "$POD" -c superset -- python3 -c '
import sys, json, urllib.request, urllib.error
body = json.dumps({"username": "mu_adm", "password": sys.stdin.read(), "provider": "db", "refresh": False}).encode()
req = urllib.request.Request("http://127.0.0.1:8088/api/v1/security/login", data=body, headers={"Content-Type": "application/json"}, method="POST")
try: print(urllib.request.urlopen(req, timeout=20).status)
except urllib.error.HTTPError as e: print(e.code)'
```

Expected:
- prints `401` (measured 2026-09-22). A `200` here means the login endpoint is
  not checking passwords -- stop and investigate before trusting Test 1.

If failed:
- Connection error -> the web pod is not serving on 8088; `kubectl logs`.

### Test 3: Regression suite

```bash
bash runbooks/tests/test-health-check-superset-fab-credential.sh
```

Expected:
- `N passed, 0 failed`, including the commissioning straw.

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| Sweep MAJOR: `... rejected for FAB user mu_adm (401)` | In-app reset, or a restore from a pre-rotation backup | §5 Example B (do not blindly re-apply the old value) |
| Sweep "Measurement did not run -- superset-fab-credential-...: no Running superset web pod" | Superset down or the selector changed | `kubectl get pods -n databases -l app.kubernetes.io/name=superset` |
| "... superset-secrets.MU_ADM_PASSWORD unreadable/empty" | SOPS decrypt failed in Flux (`kustomize-controller` logs) or key renamed | `kubectl get secret -n databases superset-secrets -o json \| python3 -c 'import sys,json; print(sorted(json.load(sys.stdin)["data"]))'` |
| "... login endpoint unreachable from inside the web pod" | gunicorn not listening on 8088, or python3 missing from the image after an upgrade | `kubectl exec ... -- sh -c 'command -v python3; curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8088/health'` |
| Probe 200 but the operator cannot log in via the UI | UI goes through Authentik (OIDC); the db provider is only reachable via the API/CLI by design | Expected -- see `docs/sops/sso-local-auth-bypass.md` |

```bash
# Quick debugging commands
kubectl get pods -n databases -l app.kubernetes.io/name=superset
kubectl logs -n databases deploy/superset --tail=50 | grep -i 'login\|auth'
python3 runbooks/policy-cli.py finding list | grep -i superset
```

---

## 8) Diagnose Examples

### Diagnose Example 1: Which copy is wrong -- SOPS or the app?

```bash
# 1. Does the SOPS value log in?   (Test 1)  -> 401
# 2. Does the value you *believe* is current log in? Paste nothing: ask the
#    person who changed it to run Test 2's snippet with their value on stdin.
# 3. Superset action log: Security -> Action Log, filter "ResetPasswordView"
```

Expected:
- 1 = 401 and 3 shows a reset -> the app moved; converge both on a NEW value (§4 Steps 1-3).
- 1 = 401 and 3 shows nothing -> a restore or a chart init re-asserted `admin`; check `init.createAdmin` in the HelmRelease and the Longhorn restore history.

If unclear:
- `superset fab list-users` in-pod: an account you did not expect means the
  table in §2 is incomplete.

### Diagnose Example 2: Is the check itself blind?

```bash
bash runbooks/tests/test-health-check-superset-fab-credential.sh     # straw must PASS
grep -n '"mu_adm|MU_ADM_PASSWORD"' runbooks/health-check.sh            # the key is in the loop
```

Expected:
- the loop names every key in §2; the straw shows the pre-fix logic misjudging drift.

If unclear:
- a key in §2 but not in the loop is documented, not measured -- add it.

---

## 9) Health Check

Runs automatically in every sweep (`runbooks/health-check.sh`, section
"Superset FAB Credential (vault-only SOPS keys)", main shell, before
`report_unmeasured`). Ad hoc:

```bash
bash runbooks/tests/test-health-check-superset-fab-credential.sh   # logic
# and §6 Test 1 for the live login
```

Expected:
- `mu_adm: 200 -- SOPS key MU_ADM_PASSWORD authenticates against Superset FAB`
- `admin: 200 -- SOPS key ADMIN_PASSWORD authenticates against Superset FAB`

---

## 10) Security Check

```bash
# No plaintext: the value never appears in git, argv, or the report
git grep -n 'MU_ADM_PASSWORD' -- ':!*.sops.yaml' | grep -v 'jsonpath\|_spec\|KEY=\|superset-secrets\.\|# '   # expect no literal values
grep -n 'superset_fab_probe' runbooks/health-check.sh | grep -c '"\$pw"'     # expect 0: the password is piped, never an argument
# The db provider is still a full bypass of Authentik -- keep it in mind
rg -n 'AUTH_TYPE' kubernetes/apps/databases/superset/app/
```

Expected:
- no plaintext secret in the repo; the password reaches the pod on stdin only;
  the report line carries a status code, never the value.
- `docs/sops/sso-local-auth-bypass.md` still applies: a valid db-provider
  password grants Admin without Authentik/MFA. That is WHY the vault copy
  must be strong (`secrets.token_urlsafe(32)`), why every local Admin must be
  in §2, and why a drift MAJOR is investigated (§5 Example B), not silenced.
- Failed probe attempts appear in Superset's action log; one per sweep is the
  expected baseline.

---

## 11) Rollback Plan

A rotation is two independent writes, so roll back the one that failed:

```bash
# SOPS side: revert the commit (never force-push; shared worktree)
git revert <rotation-sha> && git push

# App side: re-apply whatever SOPS now holds (Step 2), then Test 1
kubectl get secret -n databases superset-secrets -o jsonpath='{.data.MU_ADM_PASSWORD}' | base64 -d \
  | kubectl exec -i -n databases "$POD" -c superset -- sh -c 'superset fab reset-password --username mu_adm --password "$(cat)"'
```

If the app is unreachable and the old value must be restored urgently, the
SOPS history (`git log -p -- kubernetes/apps/databases/superset/app/secret.sops.yaml`,
decrypt with `sops -d`) is the vault -- that is the point of keeping the vault
copy correct.

---

## 12) References

- `runbooks/health-check.sh` -- `superset_fab_probe`, `superset_fab_score`
- `runbooks/tests/test-health-check-superset-fab-credential.sh`
- `docs/sops/sso-local-auth-bypass.md` -- why the db provider is a bypass
- `docs/applications.md` (superset row) -- rotation history, backup caveat
- `docs/sops/SOP-TEMPLATE.md`
- Finding `F-9d938fce`

---

## Version History

- `2026.09.22`: initial SOP (F-9d938fce). Defines the vault-only class, the
  SOPS-first rotation order, the login-based detector and its verdicts, the
  §2 registry of known keys (Superset `MU_ADM_PASSWORD`, `ADMIN_PASSWORD`).
