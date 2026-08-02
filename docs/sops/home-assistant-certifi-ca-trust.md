# SOP: Home Assistant certifi / legacy CA-trust patch

> Description: How to restore a trusted root CA that recent Home Assistant images
> dropped from their certifi bundle, so integrations whose upstream TLS chain
> terminates at that legacy root (e.g. wyzeapi → `api.wyzecam.com`) can verify
> certificates again.
> Version: `2026.08.02`
> Last Updated: `2026-08-02`
> Owner: `sre`

---

## 1) Description

Recent `ghcr.io/home-assistant/home-assistant` images ship a certifi bundle (and
Alpine `ca-certificates`) that dropped the legacy **DigiCert Global Root CA**
(the 2006 SHA-1 root), keeping only DigiCert Global Root **G2/G3**. Some upstream
APIs still serve a valid chain terminating at that legacy root — e.g.
`api.wyzecam.com` presents `*.wyzecam.com` → `DigiCert TLS RSA SHA256 2020 CA1` →
**DigiCert Global Root CA**. With the root missing, the integration fails at the
first HTTPS call with `CERTIFICATE_VERIFY_FAILED: unable to get local issuer
certificate`, even though the chain the server sends is complete.

Key non-obvious fact: **there are TWO independent TLS consumer paths in a HA pod,
and a complete fix must cover BOTH**:

1. **HA core** uses `homeassistant.util.ssl.client_context()`, which loads
   `certifi.where()` **directly** and **ignores** `SSL_CERT_FILE` /
   `REQUESTS_CA_BUNDLE`. → Fixed by redirecting `certifi.where()` to the patched
   bundle via a `sitecustomize.py` shim on `PYTHONPATH`.
2. **Third-party integrations** (e.g. `wyzeapy`) create their **own**
   `aiohttp.ClientSession()` with aiohttp's default `SSLContext`, which loads the
   **OpenSSL system store** (`/etc/ssl/cert.pem`) and **honors `SSL_CERT_FILE`**
   — it does **not** consult certifi. → Fixed by pointing `SSL_CERT_FILE` (and
   `REQUESTS_CA_BUNDLE` for requests-based libs) at the patched bundle.

So the fix is: **redirect `certifi.where()` (path 1) AND set `SSL_CERT_FILE` /
`REQUESTS_CA_BUNDLE` (path 2)** — all pointing at ONE patched bundle at a
**neutral path** (`/patched-ca/cacert.pem`, an emptyDir outside site-packages).

**HARD RULE (2026-08-02): never mount the patched bundle over certifi's own file
in site-packages.** The original implementation subPath-mounted the emptyDir file
over `.../site-packages/certifi/cacert.pem`. When certifi `2026.7.22` released,
HA's runtime installer (uv/pip) tried to upgrade certifi at boot and the atomic
rename over the mounted file failed with **EBUSY "Resource busy (os error 16)"**
— which cascaded into `Unable to install package …` for EVERY HACS integration
whose requirement chain pulls a newer certifi (`alexa_devices`,
`dirigera_platform`, `dwd_weather`, `custom_conversation` all failed setup on
every boot). The neutral-path + `certifi.where()`-shim design lets pip upgrade
certifi freely while every TLS client still sees the patched bundle — including
after the upgrade, because the shim redirects the *new* certifi too.

- Scope: `home-automation/home-assistant` (pattern reusable for any HA integration
  that breaks on a dropped legacy root)
- Prerequisites: repo `/Users/mu/code/cberg-home-nextgen`, `mise` tooling, GitOps
  push access
- Out of scope: MITM/TLS-inspection failures (those present a *different* leaf
  issuer — this SOP is only for genuinely-dropped public roots)

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Namespace | `home-automation` |
| Source of truth | `kubernetes/apps/home-automation/home-assistant/app/` |
| Extra-CA ConfigMap | `home-assistant-extra-ca` (plaintext, PUBLIC cert + `sitecustomize.py` shim — NOT SOPS) |
| Patched bundle location | `/patched-ca/cacert.pem` (emptyDir, NEUTRAL path outside site-packages) |
| Patch mechanism (path 1: HA core) | initContainer `certifi-patch` builds the bundle + `sitecustomize.py` shim; app env `PYTHONPATH=/patched-ca` redirects `certifi.where()` |
| Patch mechanism (path 2: integrations) | env `SSL_CERT_FILE=/patched-ca/cacert.pem` + `REQUESTS_CA_BUNDLE=/patched-ca/cacert.pem` on the app container |
| Critical caveat 1 | HA `client_context()` uses `certifi.where()` (ignores `SSL_CERT_FILE`); integrations' aiohttp uses the system store (honors `SSL_CERT_FILE`) — BOTH must be covered |
| Critical caveat 2 | NEVER subPath-mount over `site-packages/certifi/cacert.pem` — HA's runtime pip/uv certifi upgrade renames over it → EBUSY (os error 16) → all HACS requirements installs fail |

---

## 3) Blueprints

- Source of truth file(s):
  - `kubernetes/apps/home-automation/home-assistant/app/ca-configmap.yaml`
  - `kubernetes/apps/home-automation/home-assistant/app/helmrelease.yaml`
  - `kubernetes/apps/home-automation/home-assistant/app/kustomization.yaml`
- Required IDs/constants: the extra root PEM (a PUBLIC trust anchor; verify its
  SHA-256 fingerprint against the CA vendor's published value before committing).

Pattern (init copies the image's certifi bundle to an emptyDir at a NEUTRAL
path, appends the extra root, and installs a `certifi.where()` redirect shim;
the app container mounts the dir read-only — nothing is mounted into
site-packages):

```yaml
initContainers:
  certifi-patch:
    image: { repository: ghcr.io/home-assistant/home-assistant, tag: <same-as-app> }
    command:
      - /bin/sh
      - -c
      - |
        set -eu
        SRC="$(python3 -c 'import certifi; print(certifi.where())')"
        cp "$SRC" /patched-ca/cacert.pem
        grep -q "BEGIN CERTIFICATE" /extra-ca/digicert-global-root-ca.pem || exit 1
        printf '\n' >> /patched-ca/cacert.pem
        cat /extra-ca/digicert-global-root-ca.pem >> /patched-ca/cacert.pem
        cp /extra-ca/sitecustomize.py /patched-ca/sitecustomize.py
        # self-test the redirect exactly as the app container will see it
        GOT="$(PYTHONPATH=/patched-ca python3 -c 'import certifi; print(certifi.where())')"
        [ "$GOT" = "/patched-ca/cacert.pem" ] || { echo "shim failed: $GOT" >&2; exit 1; }
# app container mounts the patched-ca emptyDir at /patched-ca (whole dir, readOnly)
```

App-container env (path 1 shim activation + path 2 system-store fix):

```yaml
env:
  - name: SSL_CERT_FILE          # aiohttp/OpenSSL default context (integrations)
    value: "/patched-ca/cacert.pem"
  - name: REQUESTS_CA_BUNDLE     # requests-based libs
    value: "/patched-ca/cacert.pem"
  - name: PYTHONPATH             # loads sitecustomize.py → certifi.where() redirect
    value: "/patched-ca"
```

The `sitecustomize.py` shim lives in the `home-assistant-extra-ca` ConfigMap:
at interpreter startup it rebinds `certifi.where`/`certifi.contents` (and
`certifi.core.*`) to the patched bundle, guarded by try/except so a broken or
mid-upgrade certifi can never prevent Python from starting. Because the redirect
happens per-process at startup, it survives runtime certifi upgrades — a freshly
pip-installed certifi (which lacks the legacy root) is still redirected. The
init's self-test hard-fails the pod if the redirect stops working (e.g. a future
image pre-ships its own conflicting `sitecustomize`).

---

## 4) Operational Instructions

1. **Confirm it's a dropped root, not a MITM.** From a throwaway cluster pod,
   dump the served chain and confirm the leaf issuer is the legitimate CA and the
   chain terminates at a well-known public root the pod's certifi lacks.
2. **Obtain the authentic root PEM** and verify its SHA-256 fingerprint against
   the CA vendor's published value.
3. **Add the ConfigMap** `*-extra-ca` with the PUBLIC root PEM and the
   `sitecustomize.py` shim (plaintext — do NOT SOPS a public cert; do NOT name
   it `*.sops.yaml`).
4. **Add the `certifi-patch` initContainer** + `extra-ca` (configMap) and
   `patched-ca` (emptyDir) volumes; the app container mounts the emptyDir at
   `/patched-ca` (whole dir, readOnly). **Never mount over site-packages** (see
   HARD RULE above).
5. **Set `SSL_CERT_FILE` + `REQUESTS_CA_BUNDLE`** to `/patched-ca/cacert.pem`
   and `PYTHONPATH=/patched-ca` on the app container. All three are required:
   env vars cover integrations' own sessions (path 2), PYTHONPATH activates the
   `certifi.where()` shim for HA core (path 1).
6. **Validate**: `mise exec -- task kubeconform` (only pre-existing unrelated
   errors allowed).
7. **Commit + push** (GitOps); let Flux reconcile.

```bash
cd /Users/mu/code/cberg-home-nextgen
mise exec -- task kubeconform
git add kubernetes/apps/home-automation/home-assistant/app/
git commit -m "fix(home-assistant): restore <root> for <integration> TLS"
git push
```

> Rollout note: HA uses `strategy: Recreate` + hostNetwork. If the init guard has
> a bug, Flux's `upgrade.remediation.strategy: rollback` will flap
> (roll-forward/rollback) for a few minutes before settling once the template is
> correct. Fix the guard, push, and let it settle — do not manually delete pods.

---

## 5) Examples

### Example A: wyzeapi / DigiCert Global Root CA (the original case)

```bash
# Served chain from a throwaway pod (proves chain is complete, root is the legacy CA)
mise exec -- kubectl run t --rm -i --restart=Never --image=alpine:3.20 -n home-automation \
  --command -- sh -c 'apk add -q openssl >/dev/null 2>&1; \
  echo | openssl s_client -connect api.wyzecam.com:443 -servername api.wyzecam.com -showcerts 2>/dev/null \
  | grep -E "^ *[0-9]+ s:|^ *i:"'
```

### Example B: verify the fix in the live pod

```bash
POD=$(mise exec -- kubectl get pods -n home-automation -l app.kubernetes.io/name=home-assistant \
  --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n home-automation "$POD" -c app -- python3 -c '
import ssl, socket
from homeassistant.util.ssl import client_context
ctx=client_context()
with socket.create_connection(("api.wyzecam.com",443),10) as s, ctx.wrap_socket(s,server_hostname="api.wyzecam.com") as ss:
    print("TLS OK ->", ss.getpeercert()["subject"][-1])'
```

---

## 6) Verification Tests

### Test 1: patched bundle present in app container

```bash
POD=$(mise exec -- kubectl get pods -n home-automation -l app.kubernetes.io/name=home-assistant \
  --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n home-automation "$POD" -c app -- \
  grep -c "BEGIN CERTIFICATE" /patched-ca/cacert.pem
# and the certifi.where() redirect must be live:
mise exec -- kubectl exec -n home-automation "$POD" -c app -- \
  python3 -c 'import certifi; print(certifi.where())'
```

Expected:
- Count is the stock certifi count **+1** (one extra root appended).
- `certifi.where()` prints `/patched-ca/cacert.pem`.

If failed:
- Check the init log: `kubectl logs -n home-automation "$POD" -c certifi-patch`.

### Test 2: HA client_context verifies the target host

```bash
# (see Example B) — expect "TLS OK -> ...*.wyzecam.com..."
```

Expected:
- Prints `TLS OK`.

If failed:
- Re-dump the served chain (Example A); confirm the appended root is the correct
  terminating root for that chain.

### Test 3: integration aiohttp/system-store path verifies the target host

Proves the `SSL_CERT_FILE` half of the fix (the path wyzeapy-style integrations
actually use). This must pass with **no manual env** — the env is baked into the
container.

```bash
POD=$(mise exec -- kubectl get pods -n home-automation -l app.kubernetes.io/name=home-assistant \
  --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n home-automation "$POD" -c app -- printenv SSL_CERT_FILE
mise exec -- kubectl exec -n home-automation "$POD" -c app -- python3 -c '
import asyncio, aiohttp
async def main():
    async with aiohttp.ClientSession() as s:
        async with s.get("https://api.wyzecam.com/app/v2/home_page/get_object_list") as r:
            print("aiohttp default session -> HTTP", r.status)
asyncio.run(main())'
```

Expected:
- `SSL_CERT_FILE` prints the patched certifi path.
- aiohttp default session returns `HTTP 200`.

If failed:
- Confirm `SSL_CERT_FILE` is set (env missing → aiohttp falls back to the system
  store and fails). Confirm `ssl.get_default_verify_paths().cafile` equals the
  patched path.

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| `Unable to install package …: failed to rename … certifi/cacert.pem: Resource busy (os error 16)` on boot; HACS integrations fail setup | Something is mounted over `site-packages/certifi/cacert.pem` (the pre-2026.08.02 subPath pattern) — pip/uv cannot atomically replace a mounted file | Remove the site-packages mount; use the neutral-path + `sitecustomize.py` shim pattern from section 3 |
| init exits 1: "sitecustomize redirect failed" | Image now pre-ships its own `sitecustomize`/site hook shadowing ours, or ConfigMap shim missing | Inspect `python3 -c "import sitecustomize, inspect; print(inspect.getsourcefile(sitecustomize))"` in the init image; merge/rename the shim accordingly |
| init exits 1: "configMap missing a PEM certificate" | ConfigMap key/content wrong | Ensure `ca-configmap.yaml` has a valid `-----BEGIN CERTIFICATE-----` block under `digicert-global-root-ca.pem` |
| Still `CERTIFICATE_VERIFY_FAILED` after patch | Wrong terminating root appended (chain ends at a different root) | Dump served chain (Example A); append the actual terminating root |
| HR flapping roll-forward/rollback | init guard bug during a rollout under `Recreate` | Fix the guard, push; let Flux settle — do not delete pods manually |
| HA core TLS OK but an INTEGRATION still fails `CERTIFICATE_VERIFY_FAILED` | `SSL_CERT_FILE` missing — integration's own `aiohttp.ClientSession()` uses the system store, not certifi | Set `SSL_CERT_FILE=/patched-ca/cacert.pem` on the app container (path 2); push |
| HA core fails `CERTIFICATE_VERIFY_FAILED` but plain aiohttp works | `PYTHONPATH=/patched-ca` missing/overridden — the `certifi.where()` shim never loaded | Restore `PYTHONPATH`; verify `python3 -c 'import certifi; print(certifi.where())'` prints `/patched-ca/cacert.pem` in-pod |

---

## 8) Diagnose Examples

### Diagnose Example 1: confirm root is missing (not a MITM)

```bash
POD=$(mise exec -- kubectl get pods -n home-automation -l app.kubernetes.io/name=home-assistant \
  --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n home-automation "$POD" -c app -- python3 -c '
import ssl, certifi
print("G2 present:", open(certifi.where()).read().count("DigiCert Global Root G2"))
# then compare against the served chains terminating root from Example A'
```

Expected:
- certifi has G2/G3 but lacks the legacy root that the served chain terminates at.

If unclear:
- Compare against an `alpine:3.20` pod (older bundle that still trusts it).

---

## 9) Health Check

```bash
mise exec -- kubectl get pods -n home-automation -l app.kubernetes.io/name=home-assistant
mise exec -- flux get helmreleases -n home-automation home-assistant
```

Expected:
- Pod `1/1 Running`, `certifi-patch` init Completed, HelmRelease `Ready=True`.

---

## 10) Security Check

```bash
# The extra CA must be a PUBLIC cert only — no private key material
grep -E "PRIVATE KEY|BEGIN (RSA|EC|OPENSSH)" \
  kubernetes/apps/home-automation/home-assistant/app/ca-configmap.yaml || echo "OK: no private key"
# It must NOT be SOPS (public certs are not secrets) and must not be named *.sops.yaml
```

Expected:
- Only a public `CERTIFICATE` block; no private key; not SOPS-encrypted.
- No integration credential (e.g. Wyze `key_id`/`api_key`) in git — those live on
  the HA config PVC out of band, or in a `*.sops.yaml` Secret if ever moved into GitOps.

---

## 11) Rollback Plan

```bash
# Revert the fix commit(s); Flux reconciles back to the prior (unpatched) state
cd /Users/mu/code/cberg-home-nextgen
git revert <sha>
git push
```

The rollback removes the initContainer/ConfigMap; the affected integration returns
to the failing-TLS state but no data is touched (patch is a read-only certifi
overlay in an emptyDir).

---

## 12) References

- `kubernetes/apps/home-automation/home-assistant/app/ca-configmap.yaml`
- `kubernetes/apps/home-automation/home-assistant/app/helmrelease.yaml`
- `docs/sops/monitoring.md` (minimal-container caveat: use port-forward, not exec-curl)
- `docs/applications.md` (home-assistant inventory row)

---

## Version History

- `2026.07.10`: Initial SOP — certifi legacy-root-drop patch pattern, born from
  the wyzeapi / DigiCert Global Root CA fix.
- `2026.07.10`: Added the second consumer path — integrations' own
  `aiohttp.ClientSession()` use the OpenSSL system store, not certifi; a complete
  fix also requires `SSL_CERT_FILE` on the app container. Added Test 3,
  troubleshooting row, and dual-path guidance throughout.
- `2026.08.02`: **Pattern rework after certifi 2026.7.22 incident.** The subPath
  mount over `site-packages/certifi/cacert.pem` blocked HA's boot-time certifi
  upgrade (rename → EBUSY os error 16) and broke requirements install for
  alexa_devices, dirigera_platform, dwd_weather and custom_conversation. New
  pattern: patched bundle at neutral `/patched-ca/cacert.pem` +
  `SSL_CERT_FILE`/`REQUESTS_CA_BUNDLE` + `certifi.where()` redirect via
  `sitecustomize.py` on `PYTHONPATH`. Added HARD RULE: never mount into
  site-packages.
