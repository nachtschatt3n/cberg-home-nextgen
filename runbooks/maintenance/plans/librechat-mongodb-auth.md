---
plan_id: librechat-mongodb-auth
component: librechat-mongodb
pr: null                            # Hand-authored hardening change, not a version update.
kind: config
current: "auth disabled, NetworkPolicy open to all namespaces"
target: "auth enabled (SOPS secret) + NetworkPolicy scoped to librechat pods"
update_type: security
risk: medium                        # Not from blast radius -- from the datadir re-init. The
                                    # bitnami mongodb entrypoint creates users ONLY on an empty
                                    # datadir, so enabling auth on a populated volume yields a
                                    # server that starts fine and rejects every login. The wipe
                                    # is therefore mandatory, not incidental.
est_duration_min: 30
needs_reboot: false
window: "sat-early:2026-08-15"
status: scheduled
touches:
  namespaces: [ai]
  resources:
    - helmrelease/librechat
    - deployment/librechat-mongodb
    - pvc/librechat-mongodb                 # 10Gi, storageClass longhorn (DYNAMIC, reclaim=Delete)
    - networkpolicy/librechat-mongodb       # chart-generated, mongodb subchart 16.5.45
---

# librechat-mongodb — enable auth + scope the NetworkPolicy

## 1. Why

Two defects, both pre-existing, both flagged independently by three agents on
2026-08-15 and covered by **no** accepted risk:

1. **`mongodb.auth.enabled: false`.** LibreChat connects with
   `MONGO_URI = mongodb://librechat-mongodb.ai.svc.cluster.local:27017/LibreChat`
   — no credentials. Anything that can reach the Service has full read/write.
2. **The chart-generated NetworkPolicy has no `from:` selector.** The bitnami
   subchart default `networkPolicy.allowExternal: true` emits an ingress rule
   that matches every source, so *any pod in any namespace* can reach it. The
   policy exists, which makes it read as protection while granting none.

Together: an unauthenticated database reachable cluster-wide. ClusterIP only
(no ingress, no LoadBalancer), so this is not internet-exposed.

**Operator note 2026-08-15: LibreChat holds no real data.** That is what makes
the destructive path acceptable and keeps the urgency low — this is
defence-in-depth on an empty store, not an incident.

## 2. Why this was NOT done on 2026-08-15

It was ready to execute and deliberately deferred. Enabling auth requires
wiping the datadir (see `risk` above), and the session that would have run it
was inside an API session limit that had already killed four agents mid-flight.
A wipe-and-reinit interrupted between "PVC deleted" and "librechat reconnected"
leaves the app down with no operator present. The exposure is cluster-internal
and the store is empty; that trade did not favour proceeding.

Do this **in a window, attended**, or at minimum in a session with headroom.

## 3. Pre-checks

```bash
# Confirm the store really is disposable before deleting anything.
kubectl -n ai exec deploy/librechat-mongodb -- \
  mongosh LibreChat --quiet --eval 'db.getCollectionNames()'
kubectl -n ai exec deploy/librechat-mongodb -- \
  mongosh LibreChat --quiet --eval 'db.users.countDocuments({})'
```

If either shows data the operator cares about, **stop** and take a logical dump
first (`mongodump`); the Longhorn snapshot alone will not survive the PVC delete
— `reclaimPolicy=Delete` on a dynamic `longhorn` PV means deleting the PVC
destroys the volume.

## 4. Steps

1. Generate a strong password; store it SOPS-encrypted at
   `kubernetes/apps/ai/librechat/app/mongodb-secret.sops.yaml`
   (keys per bitnami: `mongodb-root-password`, `mongodb-passwords`).
   Encrypt **in place in the repo path** — see the SOPS rules in CLAUDE.md.
2. HelmRelease values:
   - `mongodb.auth.enabled: true`, `existingSecret: librechat-mongodb-auth`,
     `usernames: [librechat]`, `databases: [LibreChat]`
   - `mongodb.networkPolicy.allowExternal: false`, plus an `extraIngress` rule
     admitting only the librechat pods (`app.kubernetes.io/name: librechat`)
     in namespace `ai`.
3. Point LibreChat at the credentialed URI. `MONGO_URI` currently comes from
   ConfigMap `librechat-librechat-configenv`; move it to the secret so the
   password is not in a ConfigMap.
4. Scale librechat + mongodb to 0, delete PVC `librechat-mongodb`, reconcile.
   The subchart re-provisions an empty volume and the entrypoint creates the
   user on first boot.
5. Flux-reconcile Kustomization **then** HelmRelease (ordering matters — a
   HelmRelease reconciled first upgrades with stale values while reporting Ready).

## 5. Verification

- `kubectl -n ai exec deploy/librechat-mongodb -- mongosh --quiet --eval 'db.adminCommand({connectionStatus:1})'`
  shows an authenticated user, and an **unauthenticated** `mongosh` is refused.
- The rendered NetworkPolicy has a non-empty `from:` — verify the object, not
  the values file.
- **Negative test, the one that matters:** from a pod in another namespace,
  `nc -z librechat-mongodb.ai.svc.cluster.local 27017` must FAIL. A policy that
  renders correctly and still admits traffic is the exact failure being fixed.
- LibreChat serves 200 and a new chat persists across a pod restart.

## 6. Rollback

`git revert` the values commit + reconcile. The datadir is disposable, so
rollback is "wipe again with auth off". Note the wipe itself is **not**
reversible — that is accepted here only because the store is empty.
