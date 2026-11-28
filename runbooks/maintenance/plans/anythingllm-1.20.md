---
plan_id: anythingllm-1.20
component: anythingllm
pr: 555                               # Renovate "1.19.0 -> 1.20.0", MERGED as a7cfb7560
                                      # (2026-11-19 03:32 +0100, nightly Step-0 auto-update lane).
kind: image
current: "1.20.0"                     # live 2026-11-27: deploy image mintplexlabs/anythingllm:1.20.0, pod
                                      # anythingllm-d8b7dbcc9-rvgmj started 2026-11-19T02:34:47Z, imageID
                                      # ...@sha256:3e2b7bc8eb0f... (== the GA digest this plan targeted),
                                      # DEPLOYMENT_VERSION=1.20.0, runtime "24 0.30.0" (node 24, lancedb 0.30.0).
target: "1.20.0"                      # REMAINDER plan (re-planned 2026-11-27): the bump is done; what is left
                                      # is (a) recovering the data volume's ext4 from `shutdown` and (b) the
                                      # §4.2 contents census that never ran after the bump. No version change.
update_type: minor
risk: medium                          # The step itself is a pod re-create (Recreate, ~1-2 min). Medium because
                                      # the volume's filesystem is in ext4 `shutdown` state since ~2026-11-21
                                      # 00:00 UTC: the re-mount runs fsck, and if fsck cannot repair it the path
                                      # is a Longhorn backup restore (§5.2), which is operator-attended.
est_duration_min: 25
needs_reboot: false
touches:
  namespaces: [ai]
  resources:
    - deployment/anythingllm          # pod deleted once -> Recreate -> new pod re-mounts the volume
    - pvc/anythingllm-storage-claim   # NOT edited; detached/re-attached. Longhorn dynamic PV
                                      # pvc-b32f29a6-e7d3-49d7-879a-5c3808c6dadf (RWO, engine on k8s-nuc14-01,
                                      # replicas on nuc14-02/03).
    - volume/storage/pvc-b32f29a6-e7d3-49d7-879a-5c3808c6dadf   # re-attach; §5.2 restore only on failure
  shared: [longhorn, monitoring]      # Longhorn: a re-attach (and on failure a restore). monitoring: §4.3
                                      # reads Prometheus.
depends_on: []
conflicts_with: [longhorn-1.13.0, flux-oci-chart-sources, helm-drift-detection, kube-prometheus-stack-93.3.0]
                                      # longhorn-1.13.0: storage-engine upgrade; this plan re-attaches (and may
                                      #   restore) a Longhorn volume. Do not share a window.
                                      # flux-oci-chart-sources: rolls deployment/anythingllm in its stage 5.
                                      # helm-drift-detection: gates on "no Helm upgrade / no roll" incl. ai/anythingllm.
                                      # kube-prometheus-stack-93.3.0: §4.3 reads Prometheus/ALERTS.
exclusive: false
security_ref: null
finding_refs: [F-2d0f09e2]            # the recurring anythingllm version finding ("1.19.0 -> 1.20"). Close it
                                      # with a7cfb7560 only after §4 passes (the bump is not proven good until the
                                      # census reads the data).
capability_change: false              # The remainder changes no version, config, route or permission: a pod
                                      # re-create plus read-only verification. (The 1.20.0 capability change
                                      # itself already landed via #555.)
rollback_class: backup-restore        # A pod re-create has no git to revert. If the fsck/mount fails or the
                                      # census shows damaged data, the only path is restoring the pre-fault
                                      # Longhorn backup (§5.2).
status: draft
window: null
premises:
  - id: live-image-is-1.20.0
    why: "The bump landed via #555; if the Deployment moved again, §4.1's expected values are wrong."
    run: kubectl get deploy -n ai anythingllm -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: mintplexlabs/anythingllm:1.20.0
  - id: running-pod-is-1.20.0-digest
    why: "§4.1 compares against this digest; another digest means another image is running."
    run: kubectl get pod -n ai -l app.kubernetes.io/name=anythingllm -o jsonpath='{.items[0].status.containerStatuses[0].imageID}'
    expect_matches: 'sha256:3e2b7bc8eb0f73a130fc575f1372bd4e7189e399a63c037497fc183c141fc0ae$'
  - id: faulted-pod-still-running
    why: >-
      The reason this remainder exists: pod anythingllm-d8b7dbcc9-rvgmj (started 2026-11-19T02:34:47Z)
      holds the ext4 mount in `shutdown` state (measured in-pod 2026-11-27; the runner refuses
      `kubectl exec`, so §2.3 re-reads /proc/mounts). A different startTime means the pod was already
      re-created: §3 is done, skip to §4 or retire the plan.
    run: kubectl get pod -n ai -l app.kubernetes.io/name=anythingllm -o jsonpath='{.items[0].status.startTime}'
    expect_exact: "2026-11-19T02:34:47Z"
  - id: strategy-is-recreate
    why: "RWO Longhorn + replicas 1: RollingUpdate would Multi-Attach-deadlock (docs/sops/longhorn-rwo-multi-attach.md)."
    run: kubectl get deploy -n ai anythingllm -o jsonpath='{.spec.strategy.type}'
    expect_exact: Recreate
  - id: data-volume-healthy
    why: "A degraded Longhorn volume turns a re-attach into a data risk; healthy means the fault is above the block layer."
    run: kubectl get volume -n storage pvc-b32f29a6-e7d3-49d7-879a-5c3808c6dadf -o jsonpath='{.status.robustness}'
    expect_exact: healthy
  - id: pre-fault-backup-present
    why: >-
      §5.2's restore point: the last backup taken BEFORE the filesystem went into shutdown
      (backup 2026-11-20T23:08Z; last good app log line 2026-11-20T23:42Z).
    run: kubectl get backups.longhorn.io -n storage backup-6cf4461803b84323 -o jsonpath='{.status.state}'
    expect_exact: Completed
  - id: helmrelease-ready
    why: "A failing HR would make a post-restart failure unattributable."
    run: kubectl get helmrelease -n ai anythingllm -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/longhorn.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/backup.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-11-18"
replanned: "2026-11-27"               # in place, after plan-refine premise-fail (image already at target)
needs_replan: "premise-fail: pre-fault-backup-present: command failed (rc=1): Error from server (NotFound): backups.longhorn.io \"backup-6cf446180"
needs_replan_since: "2026-11-28"
---

# anythingllm: 1.20.0 landed via #555 — remainder: storage recovery + contents census

## 1. Summary & why held

**What happened (git + live, 2026-11-27).** The plan was written 2026-11-18 for
1.19.0 -> 1.20.0 (digest-pinned GA). Before any window ran it, Renovate opened
PR #555 and the nightly Step-0 auto-update lane merged it:
`a7cfb7560 feat(container): update mintplexlabs/anythingllm ( 1.19.0 → 1.20.0 ) (#555)`,
2026-11-19 03:32 +0100. The manifest now pins `tag: "1.20.0"` (no digest).
The pod `anythingllm-d8b7dbcc9-rvgmj` started 2026-11-19T02:34:47Z on
k8s-nuc14-01 with the exact GA digest this plan targeted (`sha256:3e2b7bc8...`),
`DEPLOYMENT_VERSION=1.20.0`, runtime `24 0.30.0`. So the plan's §3 bump and its
§4.1 artifact check are DONE. The plan's §3.2 pre-bump tarball was never taken,
and its §4.2 contents census never ran.

**The app is broken now, and the alerts do not show it.** Read-only checks on
2026-11-27:
- `/proc/mounts` in the pod: `/dev/longhorn/pvc-b32f29a6-... /app/server/storage ext4 rw,relatime,shutdown`.
  The ext4 filesystem is in **shutdown**, so every read and write returns EIO.
  `ls /app/server/storage` prints `Input/output error`.
- The census (§4.2) fails with
  `unable to open database file: /app/server/prisma/../storage/anythingllm.db`.
- App log: the background cleanup jobs ran clean through
  `2026-11-20T23:42:01Z`. From `2026-11-21T02:37:01Z` every job run logs
  `unable to open database file` or `EIO: i/o error, mkdir '/app/server/storage/generated-files'`,
  7 times a day, through today.
- What still looks green: `/api/ping` gives `{"online":true}` 200, `ALERTS{alertname=~"AnythingLLM.*"}`
  shows none firing, `AVAIL 1`, restartCount 0, the HR is Ready, and the Longhorn volume reads
  `attached/healthy`. Nightly Longhorn backups still complete (block level).

**Attribution: the bump is not the likely cause.** The pod ran 1.20.0 for about
45 hours with working storage (cleanup jobs succeeded on 11-19 and 11-20). The
filesystem then failed in the window 2026-11-20T23:42Z..2026-11-21T02:37Z. The
Longhorn backup `backup-6cf4461803b84323` completed at 23:08Z, before the fault.
The engine (`...-e-0`, longhorn-engine v1.12.1) runs on instance-manager
`instance-manager-c8e6081d...` on k8s-nuc14-01 (14 d old). The replicas are on
nuc14-02 and nuc14-03. The root cause (a block-device I/O error under the
engine, a frontend hiccup, a node event) is NOT established here. That
investigation belongs to the storage owner and is not part of this plan.

**What this remainder does:**
1. Re-create the pod once. The volume is unmounted and re-attached, and on
   NodeStage kubelet's mount-utils runs `fsck -a` on ext4 before mounting.
2. Run the 1.20.0 contents census, which was never run, against the 2026-11-18
   baseline. This proves lancedb 0.30 reads the 0.15-written table and that no
   migration ran.
3. If the volume will not mount cleanly, or the census shows damage, restore
   the pre-fault backup (§5.2, operator-attended).

**Why it still needs review:** the restore path loses any writes after
2026-11-20T23:08Z. There have been none since 23:42Z, because the filesystem
refuses writes. The restore also means rebinding a UUID PV.

## 2. Pre-checks

```bash
# 2.0 Premises (all seven must PASS)
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 runbooks/plan-premises.py anythingllm-1.20 --require-premises
# faulted-pod-still-running FAILS => the pod was already re-created: skip §3, run §4; if §4 passes, retire.

# 2.1 Pre-fault backup restorable-looking (the §5.2 source). PASS: "Completed 570425344" (size > 0).
kubectl get backups.longhorn.io -n storage backup-6cf4461803b84323 \
  -o jsonpath='{.status.state} {.status.size}{"\n"}'

# 2.2 No Longhorn work in flight on this volume (rebuilds, a Longhorn upgrade in progress).
#     PASS: exactly two lines, both "running", and the engine line "running".
kubectl get replicas.longhorn.io -n storage -l longhornvolume=pvc-b32f29a6-e7d3-49d7-879a-5c3808c6dadf \
  -o custom-columns=N:.metadata.name,NODE:.spec.nodeID,STATE:.status.currentState --no-headers
kubectl get engines.longhorn.io -n storage -l longhornvolume=pvc-b32f29a6-e7d3-49d7-879a-5c3808c6dadf \
  -o custom-columns=N:.metadata.name,STATE:.status.currentState --no-headers

# 2.3 Record the fault signature (evidence for the storage owner; read-only).
#     PASS (= the fault is still present): the error count is > 0 and the mount line contains "shutdown".
P=$(kubectl get pod -n ai -l app.kubernetes.io/name=anythingllm -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n ai "$P" -c anythingllm -- grep /app/server/storage /proc/mounts
kubectl logs -n ai "$P" -c anythingllm --since=24h | grep -c -i -E 'EIO|unable to open database'
```

## 3. Steps

There is no manifest change. The only action is one pod re-create, which the
window agent delegates to cberg-agent. The precedent is the "run once via
cberg-agent" restart in `frigate-reolink-go2rtc-flv`. A git-only alternative
would be a dummy config change that rolls the pod through reloader. That adds
a commit with no meaning, so it is not used.

```bash
# 3.1 Re-create the pod (Recreate strategy: old pod terminates, volume detaches, new pod attaches).
P=$(kubectl get pod -n ai -l app.kubernetes.io/name=anythingllm -o jsonpath='{.items[0].metadata.name}')
kubectl delete pod -n ai "$P"
kubectl wait --for=condition=Ready pod -n ai -l app.kubernetes.io/name=anythingllm --timeout=300s

# 3.2 If the new pod is stuck ContainerCreating > 5 min: read the mount error, do NOT retry blindly.
kubectl describe pod -n ai -l app.kubernetes.io/name=anythingllm | tail -20
#   "fsck found errors ... UNEXPECTED INCONSISTENCY" / "mount failed" => STOP, go to §5.2 (operator).
#   "Multi-Attach" => the strategy premise lied; STOP, see docs/sops/longhorn-rwo-multi-attach.md.
```

## 4. Verification

**4.1 The mount is clean and writable.** A `shutdown` mount still answers
`/api/ping`, so ping proves nothing here.
```bash
P=$(kubectl get pod -n ai -l app.kubernetes.io/name=anythingllm -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n ai "$P" -c anythingllm -- grep /app/server/storage /proc/mounts
kubectl exec -n ai "$P" -c anythingllm -- sh -c 'ls /app/server/storage >/dev/null && touch /app/server/storage/.rw-probe && rm /app/server/storage/.rw-probe && echo RW_OK'
kubectl get pod -n ai "$P" -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'
```
PASS requires all three:
- The mount line contains `rw` and does NOT contain `shutdown` or `ro`.
- `RW_OK` is printed.
- The imageID still ends in `sha256:3e2b7bc8eb0f73a130fc575f1372bd4e7189e399a63c037497fc183c141fc0ae`.

What failure looks like: `shutdown` in the mount line, `Input/output error`, or
`Read-only file system`. Each was measured live on 2026-11-27 or is what ext4
`errors=remount-ro` prints.

**4.2 CONTENTS census vs the 2026-11-18 baseline (never run after the bump).**
This is read-only: Prisma `count()`, LanceDB row count plus a vector search,
and one local GET. On 2026-11-27 the same script printed `CENSUS_ERROR=` with
`unable to open database file`, so the gate does fail on this fault. The
baseline below is the live 1.19.0 census from 2026-11-18, recorded in the
previous revision of this plan.

```bash
D=$(mktemp -d)
cat > "$D/allm-census.js" <<'EOF'
// Read-only census of AnythingLLM state. Prints one KEY=VALUE per line.
const { PrismaClient } = require("@prisma/client");
const lancedb = require("@lancedb/lancedb");
(async () => {
  const p = new PrismaClient({ log: [] });
  const out = {};
  out.workspaces = await p.workspaces.count();
  out.workspace_documents = await p.workspace_documents.count();
  out.workspace_chats = await p.workspace_chats.count();
  out.users = await p.users.count();
  out.system_settings = await p.system_settings.count();
  const m = await p.$queryRawUnsafe("SELECT count(*) AS n FROM _prisma_migrations WHERE finished_at IS NOT NULL");
  out.prisma_migrations = Number(m[0].n);
  await p.$disconnect();
  const db = await lancedb.connect("/app/server/storage/lancedb");
  for (const n of (await db.tableNames()).sort()) {
    const t = await db.openTable(n);
    out["lance_" + n] = await t.countRows();
    const rows = await t.query().limit(1).toArray();
    const hits = rows.length ? await t.search(Array.from(rows[0].vector)).limit(3).toArray() : [];
    out["lance_" + n + "_search_hits"] = hits.length;
  }
  const s = (await (await fetch("http://127.0.0.1:3001/api/setup-complete")).json()).results;
  out.api_vectordb = s.VectorDB; out.api_llm = s.LLMProvider; out.api_multiuser = s.MultiUserMode;
  for (const k of Object.keys(out)) console.log(k + "=" + out[k]);
})().catch(e => { console.log("CENSUS_ERROR=" + e.message); process.exit(1); });
EOF
cat > "$D/allm-pre.txt" <<'EOF'
workspaces=2
workspace_documents=293
workspace_chats=8
users=2
system_settings=5
prisma_migrations=40
lance_paperless=1241
lance_paperless_search_hits=3
api_vectordb=lancedb
api_llm=ollama
api_multiuser=true
EOF
cat > "$D/allm-compare.py" <<'EOF'
import sys
def load(p):
    d = {}
    for line in open(p):
        line = line.strip()
        if "=" in line and not line.startswith("prisma:"):
            k, v = line.split("=", 1); d[k] = v
    return d
pre, post = load(sys.argv[1]), load(sys.argv[2])
bad = []
if not pre or "CENSUS_ERROR" in pre: bad.append("PRE census empty/errored")
if not post: bad.append("POST census empty")
if "CENSUS_ERROR" in post: bad.append("POST census error: " + post["CENSUS_ERROR"])
for k, v in pre.items():
    if k not in post: bad.append(f"MISSING {k} (pre={v})")
    elif k == "workspace_chats":
        if int(post[k]) < int(v): bad.append(f"{k} shrank {v}->{post[k]}")
    elif post[k] != v: bad.append(f"{k} changed {v}->{post[k]}")
for k in post:
    if k not in pre: bad.append(f"NEW {k}={post[k]}")
print("CENSUS_FAIL\n  " + "\n  ".join(bad) if bad else f"CENSUS_OK ({len(pre)} keys identical)")
sys.exit(1 if bad else 0)
EOF
P=$(kubectl get pod -n ai -l app.kubernetes.io/name=anythingllm -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n ai -i "$P" -c anythingllm -- sh -c 'cd /app/server && node -' < "$D/allm-census.js" \
  | grep -v '^prisma:' > "$D/allm-post.txt"
cat "$D/allm-post.txt"
python3 "$D/allm-compare.py" "$D/allm-pre.txt" "$D/allm-post.txt"
```
PASS is `CENSUS_OK (11 keys identical)` with exit 0. `workspace_chats` may
only grow. Which failure points where:
- `CENSUS_ERROR` naming the database or EIO: the mount is still bad. Go to §5.2.
- `prisma_migrations` changed: a migration ran that the 2026-11-18 diff did not
  find (`v1.19.0..v1.20.0 -- server/prisma` was empty). Record it. This is not
  a rollback trigger on its own.
- `MISSING lance_paperless`, a changed count, `search_hits` not 3, or a lance
  `CENSUS_ERROR`: lancedb 0.30 cannot read the table (upstream #7093 risk), or
  fsck dropped data. Go to §5.2. Last fallback: the table is derived and can be
  re-embedded from Paperless.
- `workspace_documents` / `users` / `system_settings` / `workspaces` changed:
  fsck truncated SQLite, or the server booted on fresh state. Go to §5.2.

The compare script's negative controls were run 2026-10-27: pre vs pre gives
OK; a tampered post gives FAIL with rc 1; an empty pre gives FAIL. An empty
post now also fails, via the `POST census empty` line added in this revision.

**4.3 Alerts, restarts, and no new I/O errors after the next background-job tick.**
Wait until the next scheduled cleanup job has run (they log at about :37 and
:41 past 02/10/14/18 UTC). Then:
```bash
P=$(kubectl get pod -n ai -l app.kubernetes.io/name=anythingllm -o jsonpath='{.items[0].metadata.name}')
kubectl logs -n ai "$P" -c anythingllm | grep -c -i -E 'EIO|unable to open database'
kubectl logs -n ai "$P" -c anythingllm | grep -c -i 'Worker for job "cleanup-'
kubectl get pod -n ai "$P" -o jsonpath='{.status.containerStatuses[0].restartCount}{"\n"}'
kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=kube_deployment_status_replicas_available%7Bnamespace%3D%22ai%22%2Cdeployment%3D%22anythingllm%22%7D' \
  | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print('AVAIL', r[0]['value'][1] if r else 'ABSENT')"
```
PASS: `0` I/O errors, a cleanup-job count `>= 1` (it proves the job ran, so the
0 is not vacuous), restartCount `0`, `AVAIL 1`. `ABSENT` is a FAIL.

**4.4 Close out.**
- `policy-cli.py finding close F-2d0f09e2 --commit a7cfb7560` (the bump commit).
- Set `status: executed` in this plan, and note the §4.2 output.

## 5. Rollback

**5.1 Pod re-create, nothing to revert.** If the new pod fails for a reason
other than storage (crash loop on 1.20.0, Node 24 OOM), the image rollback is
`git revert a7cfb7560` and push. That changes the pin back to `tag: "1.19.0"`;
check it with `git show a7cfb7560`. This plan does NOT pre-authorise it.
Without the §3.2 tarball there is no proof that lancedb 0.15 reads what 0.30
wrote. Run the §4.2 census on 1.19.0 afterwards. A lance `CENSUS_ERROR` there
means §5.2.

**5.2 Restore the pre-fault Longhorn backup (operator-attended).** Use this
when the volume will not mount after fsck, or §4.2 shows damage.
- Source: backup `backup-6cf4461803b84323` of volume
  `pvc-b32f29a6-e7d3-49d7-879a-5c3808c6dadf` (Completed, 2026-11-20T23:08:27Z,
  570425344 bytes). This is the last backup BEFORE the filesystem went into
  shutdown. Do not restore any later backup. They are block copies of a
  filesystem that had already shut down, and the newest is not the cleanest.
- Procedure: `docs/sops/backup.md` "Restore from Backup". Restore it to a new
  volume `restored-anythingllm-storage`, then rebind the PV/PVC. The PVC
  `anythingllm-storage-claim` is chart-created on a UUID PV, so the rebind means
  scaling the Deployment to 0 and editing the claim. Keep the original volume
  until the operator says to delete it (a Longhorn volume, not CIFS, so the
  CIFS pre-flight rule does not apply; never delete it within this plan anyway).
- Data cost: any writes after 23:08Z on 11-20. App logs show the last
  successful job at 23:42Z, and the filesystem has refused writes since the
  fault.
- Confirm: §4.1 and §4.2 pass on the restored volume.

## 6. Interference notes

- **Outage:** about 1–2 minutes of the AnythingLLM UI/API (Recreate). Nothing
  in-cluster calls AnythingLLM. The UI has effectively been down since
  2026-11-21, because every storage read fails.
- **Longhorn:** this plan re-attaches one volume, and may restore one. Do not
  run it in the same window as `longhorn-1.13.0`. Do not run it while a
  rebuild runs on this volume (§2.2).
- **Ordering:** run after the 23:00 UTC Longhorn backup job has finished. Its
  snapshot would race the detach.
- **Execution class:** `capability_change: false`, `rollback_class:
  backup-restore`. The happy path is one pod delete. The failure path is an
  operator restore. It fits nightly only if the window agent's class rules
  allow backup-restore unattended. Otherwise use the next attended slot. The
  service has been degraded for 6 days, so the next available window is
  appropriate. Do not wait for a far-off Sunday.
- **Repo corrections (not acted on; for the sweep/operator):**
  1. **Monitoring blind spot.** A shutdown filesystem under a Ready pod went
     unseen for 6 days. `/api/ping` and the readiness probe stay green, the
     AnythingLLM alert rules only cover crash/not-ready/restart, and Longhorn
     reports the volume `healthy`. A probe or alert that reads storage is
     needed, e.g. `/api/setup-complete`, which touches the DB, or a log-based
     EIO alert. It should cover every Longhorn-backed app: the same fault
     class could be sitting on other volumes behind green probes. The sweep
     should check `/proc/mounts` for `shutdown` / `ro` across Longhorn mounts.
  2. **Root cause of the ext4 shutdown** (2026-11-20T23:42Z..2026-11-21T02:37Z,
     engine on k8s-nuc14-01) is not investigated here. Kernel logs from Talos
     would show it, but they are not shipped (see the node-reboot logging-gap
     memory). That is for the storage owner.
  3. `runbooks/maintenance/plans/anythingllm-1.19.md` is still `status: draft`,
     though 1.19.0 landed via #446 (F-4e9b4d10). It should be marked
     superseded.
