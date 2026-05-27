---
title: iCloud cookie rotation
last-updated: 2026-05-28
---

# iCloud cookie rotation (mandarons/icloud-drive)

When `icloud-docker-mu` logs `cookie pcs key is corrupt (INCORRECT_PCS_KEY)` or 530 auth failures, the saved Apple session has expired. Rotation requires interactive Apple SMS 2FA — only the operator can complete it.

## Pre-flight

```bash
NS=backup
POD=$(kubectl -n $NS get pod -l app.kubernetes.io/name=icloud-docker-mu -o name | head -1)
kubectl -n $NS exec $POD -- ls -la /config/session_data
# expect: mathiasuhlmecom + mathiasuhlmecom.session
```

## Rotate

```bash
# 1) Delete stale session files (in-place; PVC survives the restart)
kubectl -n $NS exec $POD -- sh -c 'rm -f /config/session_data/mathiasuhlmecom*'

# 2) Restart the deployment so the next start prompts for 2FA
kubectl -n $NS rollout restart deploy/icloud-docker-mu
kubectl -n $NS rollout status deploy/icloud-docker-mu --timeout=60s

# 3) Attach to the new pod's TTY (interactive). The container will print
#    "Two-step authentication required. Enter the code you received:".
NEW_POD=$(kubectl -n $NS get pod -l app.kubernetes.io/name=icloud-docker-mu -o name | head -1)
kubectl -n $NS attach -it $NEW_POD
# Apple sends an SMS to the operator's primary number.
# Type the 6-digit code + Enter, then detach with Ctrl-P Ctrl-Q.
```

## Verify

```bash
# Logs should show "Syncing drive..." with no INCORRECT_PCS_KEY
kubectl -n $NS logs $NEW_POD --tail=20 | grep -iE "syncing|incorrect|530"

# Session files re-created with current mtime
kubectl -n $NS exec $NEW_POD -- ls -la /config/session_data
```

## Notes

- The mandarons/icloud-drive image stores sessions at `/config/session_data/`, **not** `/icloud/cookies/` (earlier docs were wrong).
- Apple's session typically lasts 30-60 days before another rotation is required.
- Credentials (`SECRET_ICLOUD_USERNAME` / `SECRET_ICLOUD_PASSWORD`) live in `kubernetes/apps/backup/icloud-docker-mu/app/secret.sops.yaml`. They do **not** change during rotation — only the session token does.
- If `attach` shows no 2FA prompt, the container has already entered a sync loop. Restart the deployment again and attach faster, or `exec -it ... -- sh` and re-run the icloud auth binary by hand.
