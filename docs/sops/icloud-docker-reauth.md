# SOP: iCloud Docker Re-authentication (2FA session recovery)

> Description: Recover the `icloud-docker-mu` (mandarons/icloud-drive) Apple session when it expires, including the modern-2FA flow that the bundled `icloud` CLI gets wrong, and the quota-exhaustion mitigation (stop the retry loop before re-auth).
> Version: `2026.06.13`
> Last Updated: `2026-06-13`
> Owner: `operator`

---

## 1) Description

`icloud-docker-mu` keeps a local mirror of iCloud Drive. Its Apple session
expires every ~30-60 days; when it does, every sync cycle (~10 min) fails with
`Authentication required for Account. (421)` / `2FA is required. Please log in.`
and the container loops, re-attempting auth on each cycle.

This SOP covers re-authenticating the session. The account uses **modern 2FA**
(`hsaVersion 2`), and the re-auth must be done **interactively** by the operator
(only they can approve the iPhone 2FA push and read the code).

- Scope: `backup` namespace, deployment `icloud-docker-mu`, session PVC
  `icloud-docker-mu-session` (CIFS, **ReadWriteOnce**).
- Prerequisites: `kubectl` + `flux` (via mise shims), operator's Apple device to
  approve the 2FA push, the Apple ID + password already in the SOPS secret.
- Out of scope: changing Apple credentials (separate — edit `secret.sops.yaml`).

### Why the bundled `icloud` CLI fails

`icloudpy` 0.8.0's `icloud` command checks `requires_2sa` **before**
`requires_2fa`. On a modern-2FA account both are `True`, so it takes the dead
**legacy two-step (2SA)** branch and prints
`Two-step authentication required. Please enter validation code`. That branch
needs enumerable trusted SMS devices (this account has **0**), so it never
pushes and never completes. We bypass it with a tiny script that drives the
**2FA** path directly (`validate_2fa_code` + `trust_session`).

### The retry-storm / quota trap

Apple rate-limits 2FA verification-code sends to a handful per day. If the
container is left looping, it exhausts the quota and Apple **silently stops
pushing to every device** while still reporting `requires_2fa: True`. Symptom:
no push on iPhone **or** Mac, yet `me.com` may have worked earlier. **Always
stop the loop first** (scale to 0 + suspend Flux), then re-auth once.

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Namespace | `backup` |
| Deployment | `icloud-docker-mu` |
| HelmRelease | `icloud-docker-mu` (Flux-managed) |
| Session dir | `/config/session_data` (PVC `icloud-docker-mu-session`, CIFS, RWO) |
| Session files | `<appleid-slug>` + `<appleid-slug>.session` (slug = Apple ID with `@`/`.` stripped) |
| Credentials | secret `icloud-docker-mu-secrets` → `SECRET_ICLOUD_USERNAME`, `SECRET_ICLOUD_PASSWORD` |
| CIFS file owner | uid/gid **1000** (real pod remaps `abc` 911→1000 via `PUID=1000`) |
| Auth library | `icloudpy` 0.8.0 (endpoint `idmsa.apple.com/appleauth/auth`) |
| Session lifetime | ~30-60 days |

---

## 3) Blueprints

- App manifests: `kubernetes/apps/backup/icloud-docker-mu/app/`
  (`helmrelease.yaml`, `secret.sops.yaml`, `configmap.sops.yaml`, `pvc.yaml`).
- Credentials source of truth: `kubernetes/apps/backup/icloud-docker-mu/app/secret.sops.yaml`
  (SOPS-encrypted; never edit decrypted outside the repo path).

The re-auth pod and script below are **ephemeral / not committed** — spawn them
on demand, delete when done.

### Re-auth pod manifest

A dedicated throwaway pod is required because the session PVC is **RWO** (only
one pod can mount it) and must run as **uid 1000** so the new session files are
owned correctly (a `sleep` override skips the image's `PUID` remap, leaving
`abc` at its image-default uid 911 → CIFS write `Permission denied`).

```bash
cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: icloud-reauth
  namespace: backup
  labels:
    app.kubernetes.io/name: icloud-reauth
spec:
  restartPolicy: Never
  securityContext:
    runAsUser: 1000
    runAsGroup: 1000
    fsGroup: 1000
  containers:
    - name: app
      image: mandarons/icloud-drive:latest
      command: ["sleep", "infinity"]
      env:
        - name: HOME
          value: /tmp
      envFrom:
        - secretRef:
            name: icloud-docker-mu-secrets
      volumeMounts:
        - name: session
          mountPath: /config/session_data
  volumes:
    - name: session
      persistentVolumeClaim:
        claimName: icloud-docker-mu-session
EOF
kubectl -n backup wait --for=condition=Ready pod/icloud-reauth --timeout=120s
```

### Re-auth script (`/tmp/reauth2fa.py`)

Reads the Apple ID + password from the secret-provided env vars (no PII in the
repo). Drives the modern-2FA flow directly.

```bash
kubectl -n backup exec -i icloud-reauth -c app -- sh -c 'cat > /tmp/reauth2fa.py' <<'PY'
import os, sys
from icloudpy import ICloudPyService

user = os.environ["SECRET_ICLOUD_USERNAME"]
pw = os.environ["SECRET_ICLOUD_PASSWORD"]
api = ICloudPyService(user, pw, cookie_directory="/config/session_data")

if api.requires_2fa:
    print(">> Modern 2FA required. Apple just pushed a 6-digit code to your trusted devices.")
    code = input("Enter the 6-digit code shown on your device: ").strip()
    if not api.validate_2fa_code(code):
        print("!! Code rejected by Apple."); sys.exit(1)
    print(">> Code accepted.")
    if not api.is_trusted_session:
        print(">> Trusting/saving session...")
        print(">> trust_session:", api.trust_session())
    else:
        print(">> Session already trusted.")
elif api.requires_2sa:
    print("!! Apple fell back to legacy 2SA with no trusted devices -- quota likely still throttled; wait and retry."); sys.exit(2)
else:
    print(">> Already authenticated, no challenge needed.")

print(">> Final: requires_2fa =", api.requires_2fa, "| is_trusted_session =", api.is_trusted_session)
PY
```

---

## 4) Operational Instructions

### Step 1 — Stop the retry loop (mandatory, before anything else)

```bash
export PATH="$HOME/.local/share/mise/shims:$PATH"
kubectl -n backup scale deploy icloud-docker-mu --replicas=0
flux suspend helmrelease icloud-docker-mu -n backup   # stops the 30-min reconcile re-scaling to 1
kubectl -n backup wait --for=delete pod -l app.kubernetes.io/name=icloud-docker-mu --timeout=90s
```

### Step 2 — Let the 2FA quota reset (if pushes are dead)

If a re-auth attempt shows **no push on any device**, the daily 2FA send quota
is exhausted. Wait until `me.com` login pushes to the iPhone again (a few hours,
sometimes next day). The loop is now stopped, so nothing re-burns the quota.

### Step 3 — Spawn the re-auth pod + script

Apply the pod manifest and write the script (both in section 3).

### Step 4 — Re-authenticate (interactive)

```bash
export PATH="$HOME/.local/share/mise/shims:$PATH"
kubectl -n backup exec -it icloud-reauth -c app -- python3 /tmp/reauth2fa.py
```

Approve the iPhone push, type the 6-digit code, Enter. Expect
`Final: requires_2fa = False | is_trusted_session = True`.

### Step 5 — Tear down + restore service (mind the RWO ordering)

The session PVC is RWO — **delete the re-auth pod BEFORE scaling the app up**,
or the app pod can't mount the volume.

```bash
kubectl -n backup delete pod icloud-reauth
flux resume helmrelease icloud-docker-mu -n backup   # scales back to 1
kubectl -n backup rollout status deploy/icloud-docker-mu --timeout=120s
```

### Step 6 — Clear the accepted-risk (if one was opened)

If the outage was parked under an AR (e.g. AR-044), disable it after recovery:

```bash
# via runbooks/policy-cli.py risk disable AR-NNN  (see docs/sops/policy-cli.md)
```

---

## 5) Examples

### Example A: routine expiry, quota healthy

1, 3, 4, 5 above in one sitting — the push arrives on the first attempt, no wait.

### Example B: quota exhausted by a retry storm (the 2026-06-13 case)

`icloudpy` reports `requires_2fa: True` but **no push anywhere**. Stop the loop
(step 1), park under an AR with a revisit date, wait for the quota to reset
(step 2), then complete steps 3-6. Confirm the throttle cleared by checking that
`me.com` pushes to the iPhone again before retrying.

---

## 6) Verification Tests

### Test 1: auth state is clean

```bash
kubectl -n backup exec -i icloud-reauth -c app -- python3 - <<'PY'
import os
from icloudpy import ICloudPyService
api = ICloudPyService(os.environ["SECRET_ICLOUD_USERNAME"], os.environ["SECRET_ICLOUD_PASSWORD"], cookie_directory="/config/session_data")
print("requires_2fa:", api.requires_2fa, "is_trusted_session:", api.is_trusted_session)
PY
```

Expected:
- `requires_2fa: False is_trusted_session: True`

If failed:
- Quota likely still throttled (2SA fallback) — wait and retry per step 2.

### Test 2: sync recovers after restart

```bash
NEW=$(kubectl -n backup get pod -l app.kubernetes.io/name=icloud-docker-mu -o name | head -1)
kubectl -n backup logs $NEW --tail=30 | grep -iE "syncing|incorrect|530|421|2fa"
```

Expected:
- `Syncing ...` lines, **no** `421` / `2FA is required` / `INCORRECT_PCS_KEY`.

If failed:
- Re-auth didn't persist; re-run from step 3.

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| CLI prints `Two-step authentication required. Please enter validation code` | bundled `icloud` CLI takes the dead 2SA branch | Use `reauth2fa.py` (drives 2FA directly), not the `icloud` CLI |
| No push on iPhone **or** Mac, `requires_2fa: True` | Apple 2FA send-quota exhausted by the retry loop | Stop the loop (step 1), wait for reset (step 2), retry once |
| `PermissionError: ... /config/session_data/...session` | re-auth pod ran as `abc` uid 911; CIFS owns files as 1000 | Run the pod as `runAsUser: 1000` (manifest in §3), not root + su-exec |
| App pod stuck `ContainerCreating`, volume in use | `icloud-reauth` still holds the RWO PVC | Delete `icloud-reauth` before scaling the app up |
| `Authentication required for Account. (421)` loop | session expired | Full SOP from step 1 |

---

## 8) Diagnose Examples

### Diagnose Example 1: is it 2FA or genuine 2SA?

```bash
kubectl -n backup exec -i icloud-reauth -c app -- python3 - <<'PY'
import os
from icloudpy import ICloudPyService
api = ICloudPyService(os.environ["SECRET_ICLOUD_USERNAME"], os.environ["SECRET_ICLOUD_PASSWORD"], cookie_directory="/tmp/diag")
print("requires_2fa:", api.requires_2fa, "requires_2sa:", api.requires_2sa,
      "hsaVersion:", api.data.get("dsInfo", {}).get("hsaVersion"),
      "num_trusted_devices:", len(api.trusted_devices or []))
PY
```

Expected:
- `requires_2fa: True ... hsaVersion: 2 num_trusted_devices: 0` → modern 2FA; the
  push path is correct and a missing push means quota throttle, not 2SA.

If unclear:
- `hsaVersion: 1` with devices listed → genuinely legacy 2SA (different account);
  the SMS-to-device flow would apply instead.

### Diagnose Example 2: confirm the quota throttle cleared

```bash
# Operator-side: log into https://www.icloud.com and confirm the iPhone push appears.
# If me.com no longer pushes either, the quota is still exhausted -> wait longer.
```

---

## 9) Health Check

```bash
export PATH="$HOME/.local/share/mise/shims:$PATH"
kubectl -n backup get deploy icloud-docker-mu -o jsonpath='replicas={.spec.replicas}{"\n"}'
POD=$(kubectl -n backup get pod -l app.kubernetes.io/name=icloud-docker-mu -o name | head -1)
kubectl -n backup logs $POD --tail=50 | grep -ciE "421|2fa is required"
```

Expected:
- `replicas=1`, count `0` of `421`/`2FA is required` in recent logs.

The daily sweep flags this via the `health` finding
`icloud-docker-mu recent log errors: N` — a non-zero count after a session
expiry is the trigger to run this SOP.

---

## 10) Security Check

```bash
# No Apple ID / password should ever land in the repo
rg -n "@me\.com|SECRET_ICLOUD_PASSWORD\s*[:=]" docs/ runbooks/ kubernetes/ \
  --glob '!**/*.sops.yaml' || echo "clean"
```

Expected:
- `clean` — Apple ID and password live only in the SOPS secret; the re-auth pod
  reads them from env, and this SOP hardcodes neither.
- The `icloud-reauth` pod is ephemeral and must be deleted after use (§5/step 5).

---

## 11) Rollback Plan

Re-auth is non-destructive (it only writes session cookies). If a run leaves the
session worse off, wipe and retry:

```bash
export PATH="$HOME/.local/share/mise/shims:$PATH"
# (loop already stopped) clear stale cookies, keep lost+found
kubectl -n backup exec icloud-reauth -c app -- sh -c 'rm -f /config/session_data/*.session /config/session_data/[!l]*'
# then re-run step 4
```

To abandon and restore the prior (broken-but-running) state:

```bash
kubectl -n backup delete pod icloud-reauth --ignore-not-found
flux resume helmrelease icloud-docker-mu -n backup
```

---

## 12) References

- `runbooks/icloud-cookie-rotation.md` (older quick-rotation note; superseded by
  this SOP for 2FA accounts)
- `kubernetes/apps/backup/icloud-docker-mu/app/` (manifests + SOPS secret)
- `docs/sops/policy-cli.md` (AR lifecycle — park/disable accepted risks)
- `docs/sops/cifs-mount-options.md` (CIFS ownership/`uid=1000` context)

---

## Version History

- `2026.06.13`: Initial SOP. Documents the modern-2FA re-auth flow that bypasses
  the broken `icloud` 2SA CLI, the quota-exhaustion mitigation (stop loop +
  suspend Flux before re-auth), the uid-1000 RWO re-auth pod, and the AR-044
  revisit procedure (2026-06-18).
