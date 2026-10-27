---
plan_id: anythingllm-1.19
component: anythingllm
pr: 446                               # Renovate "update mintplexlabs/anythingllm ( 1.18.0 -> 1.19.0 )",
                                      # MERGEABLE, all 4 checks green (Flate Render Gate incl.) 2026-10-27.
                                      # NOT merged by this plan: it pins the tag without a digest; §3.3 lands
                                      # the digest-pinned equivalent and §3.6 closes #446.
kind: image
current: "1.18.0"                     # live 2026-10-27: deploy image mintplexlabs/anythingllm:1.18.0,
                                      # pod imageID ...@sha256:5461782e7db4... (== Hub 1.18.0 == Hub 1.18)
target: "1.19.0@sha256:daf5a6ae9d363ed578e7d41e2d0668c7eaa604bd90b0ff27435f893b0906833e"
                                      # fixed GA tag replacing the floating `1.19` the sweep reported.
                                      # Hub 2026-10-27: 1.19 == 1.19.0 == latest == sha256:daf5a6ae...;
                                      # 1.19.1 -> 404. GitHub v1.19.0 isPrerelease=false, "Latest".
update_type: minor
risk: low                             # single internal RAG app, own PVC, 0 prisma migrations and no
                                      # vector-DB dependency change in v1.18.0..v1.19.0 (§1), Recreate,
                                      # local tarball + nightly Longhorn backup.
est_duration_min: 25
needs_reboot: false
touches:
  namespaces: [ai]
  resources:
    - helmrelease/anythingllm         # values.image.tag edit (the only file change)
    - deployment/anythingllm          # Recreate -> ~1-2 min outage of the RAG UI/API
    - pvc/anythingllm-storage-claim   # NOT edited; re-mounted (Longhorn dynamic PV
                                      # pvc-b32f29a6-e7d3-49d7-879a-5c3808c6dadf, RWO)
  shared: []                          # HTTPRoute untouched (no gateway/envoy change); no shared DB (own
                                      # SQLite + LanceDB); the Ollama host is only called, not changed;
                                      # Longhorn: a re-attach, no volume operation.
depends_on: []
conflicts_with: [flux-oci-chart-sources, helm-drift-detection, flux-reconciler-impersonation, longhorn-1.13.0]
                                      # flux-oci-chart-sources: re-points the mintplex-labs HelmRepository
                                      #   that serves this HR's chart (sun-attended:2026-11-22).
                                      # helm-drift-detection: adds driftDetection to every HR incl.
                                      #   ai/anythingllm and gates on "no Helm upgrade happened" — this
                                      #   plan IS a Helm upgrade of that HR (sat-attended:2026-11-07).
                                      # flux-reconciler-impersonation: new reconciler SA for ns ai (blocked).
                                      # longhorn-1.13.0: storage-engine upgrade; this plan re-attaches a
                                      #   Longhorn volume and §5.3 restores from Longhorn (sun 2026-11-15).
                                      # No open kube-prometheus-stack plan exists (checked 2026-10-27);
                                      #   add any new one here, §4.4 reads Prometheus.
exclusive: false
security_ref: F-5af54d38              # security driver; detail lives on the DB record only.
finding_refs: [F-5af54d38, F-2d0f09e2]
                                      # `policy-cli.py finding list --grep anythingllm` 2026-10-27:
                                      # F-5af54d38 = the security finding on the 1.18.0 image (newer tag
                                      # available); F-2d0f09e2 = the version finding "1.18.0 -> 1.19".
                                      # The AR-029 rows (F-dc34a0f6, F-e958e538) are register entries,
                                      # not this plan's driver.
capability_change: true               # TRUTHFUL, not defensive: 1.19.0 ships an embedded inference
                                      # engine (Lemonade/llama.cpp, gated on ENABLE_BUILT_IN_LLM, which we
                                      # do NOT set), admin-visible colour palettes / tabbed branding
                                      # settings, a Mistral thinking toggle, and changes behaviour: JSON/
                                      # text request bodies capped at 100 MB (was 3 GB, #6729), the
                                      # open-computer component removed from the repo (#6727).
rollback_class: git-revert            # no forward-only step: 0 files under server/prisma/ in
                                      # v1.18.0..v1.19.0 (full git diff, §1); §4.2 FAILS if the migration
                                      # count moves, and the §3.2 tarball covers that case (§5.2).
review: null
status: draft
window: null
premises:
  # All five run green 2026-10-27 while writing (plan-premises.py anythingllm-1.19 --require-premises).
  - id: live-image-still-1.18.0
    why: >-
      `current:` and the rollback target claim 1.18.0. If the Deployment already
      moved (Step-0 lane or a merged #446), the baseline and revert target are wrong.
    run: kubectl get deploy -n ai anythingllm -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: mintplexlabs/anythingllm:1.18.0
  - id: manifest-pin-still-1.18.0
    why: "§3.3's sed anchors on the exact string `tag: \"1.18.0\"`; a changed pin makes it a silent no-op."
    run: grep -c 'tag. "1.18.0"' /Users/mu/code/cberg-home-nextgen/kubernetes/apps/ai/anythingllm/app/helmrelease.yaml
    expect_exact: "1"
  - id: helmrelease-ready
    why: "A HelmRelease already failing would make a post-upgrade failure unattributable."
    run: kubectl get helmrelease -n ai anythingllm -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: strategy-is-recreate
    why: >-
      RWO Longhorn PVC + replicas 1: RollingUpdate would Multi-Attach-deadlock
      (docs/sops/longhorn-rwo-multi-attach.md). The postRenderer forces Recreate;
      if that patch stopped applying, do not roll.
    run: kubectl get deploy -n ai anythingllm -o jsonpath='{.spec.strategy.type}'
    expect_exact: Recreate
  - id: data-volume-healthy
    why: "The upgrade re-attaches this volume; a degraded volume turns a re-attach into a data risk."
    run: kubectl get volume -n storage pvc-b32f29a6-e7d3-49d7-879a-5c3808c6dadf -o jsonpath='{.status.robustness}'
    expect_exact: healthy
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/longhorn.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/backup.md
generated: "2026-10-27"
---

# anythingllm: 1.18.0 -> 1.19.0 (digest-pinned GA for the floating `1.19`)

## 1. Summary & why held

AnythingLLM (namespace `ai`, Mintplex chart `anythingllm` 1.0.0, image
`mintplexlabs/anythingllm`) is the internal multi-user RAG workspace. Its state
is one RWO Longhorn PVC `anythingllm-storage-claim` (chart-created, dynamic PV
`pvc-b32f29a6-...`) at `/app/server/storage`: Prisma/SQLite `anythingllm.db`
and LanceDB (`lancedb/paperless.lance`, 1241 vectors). LLM + embeddings go to
the shared Ollama host, which this plan does not touch.

**Why held.** The sweep's target was `1.19`, fewer components than the pinned
`1.18.0`: a floating series pointer. **The hold is resolvable: a fixed GA tag
exists**, and Renovate PR #446 already proposes it. Measured 2026-10-27
(registry-1 manifest HEAD, OCI index digest; Hub tag API; GitHub):

| Probe | Result |
|---|---|
| `mintplexlabs/anythingllm:1.19.0` | 200, `sha256:daf5a6ae9d363ed5...` (pushed 2026-10-26T16:17Z) |
| `:1.19` and `:latest` | 200, **same** `sha256:daf5a6ae...` |
| `:1.19.1` | 404 |
| `:1.18.0` / `:1.18` | 200, `sha256:5461782e7db4...` (== running pod imageID) |
| GitHub `v1.19.0` | published 2026-10-26T16:14Z, `isPrerelease=false`, **Latest** |

This plan pins `1.19.0@sha256:daf5a6ae...` (house pattern, e.g. traccar,
teslamate). The floating `1.19` is never written. `pg-*`/`render-*`/`railway-*`
tags are other deployment variants, not candidates. `helm template` of chart
1.0.0 with the digest-pinned tag renders
`image: "mintplexlabs/anythingllm:1.19.0@sha256:daf5a6ae..."` (verified
2026-10-27; the chart joins `repository:tag`).

**Release notes v1.19.0** (no "breaking"/"migration" section). Headline
features: *"Built-in LLM for Docker"* (#6719, Lemonade + llama.cpp in the
container; *"The built-in LLM is off by default. Turn it on by starting the
container with `-e ENABLE_BUILT_IN_LLM=true`"*) and instance colour palettes
(#6796). About 45 fixes. The ones that touch our wiring, each checked in code:

- **#6729 "Cap request body size"**: JSON/text/urlencoded bodies drop from a
  3 GB limit to 100 MB (`SERVER_BODY_LIMIT` override); *"Binary file uploads
  are handled by multer (multipart/form-data) and are unaffected"*. No in-cluster
  client posts bodies anywhere near that size.
- **#6766 "connect to the document collector on 127.0.0.1"**: a one-line
  client-side change in `server/utils/collectorApi/index.js`
  (`http://0.0.0.0:` -> `http://127.0.0.1:`). `collector/index.js` is
  **unchanged** in the range and still calls `.listen(COLLECTOR_PORT)` with no
  host, so it binds all interfaces. Our readiness/liveness probes hit
  `:8888/v1/api/health` (the collector) on the pod IP, so they keep working.
  §3.5 would show this as NotReady if it were wrong.
- **#6816 "fix(ollama): keep context windows when one model show fails"**: on
  our Ollama path, but a robustness fix only.
- **#6675 Weaviate -> weaviate-client v3**: we run `VECTOR_DB=lancedb`.
- **#6727 open-computer removed** (moved to its own repo): 56 of the changed
  files. It is not configured here.

**Data store / rollback evidence** (this decides `rollback_class`). The GitHub
compare API caps at 300 files (it hit the cap), so I used a full clone:
`git diff --stat v1.18.0 v1.19.0` = 4393 files (mostly the open-computer
removal and frontend icon assets).

- `git diff --name-status v1.18.0 v1.19.0 -- server/prisma` -> **empty**. No
  schema change, no new migration. Live baseline `_prisma_migrations` = 40
  finished rows (unchanged since 1.16.2).
- `server/` + `collector/` + `frontend/package.json`: the only dependency
  change is `weaviate-ts-client ^1.4.0` -> `weaviate-client 3.9.0`.
  `@lancedb/lancedb` and `@prisma/client` are unchanged, so the on-disk formats
  cannot move.
- `docker/Dockerfile`: adds `libvulkan1 mesa-vulkan-drivers` (for the opt-in
  engine) and `DEPLOYMENT_VERSION=1.19.0`. The entrypoint is unchanged.

So reverting to 1.18.0 with `git revert` is a complete rollback. §4.2 proves
this after the fact.

**Security driver:** `security_ref: F-5af54d38` (detail on the DB record only).
This bump is the "bump to a newer upstream tag" remedy that finding asks for.
Re-scan after the window to confirm it.

## 2. Pre-checks

Run from `/Users/mu/code/cberg-home-nextgen` in zsh, after the 03:00
`storage/daily-backup-all-volumes` job has finished.

```bash
cd /Users/mu/code/cberg-home-nextgen

# 2.0 Premises (all five must PASS)
.venv/bin/python3 runbooks/plan-premises.py anythingllm-1.19 --require-premises

# 2.1 Target is still the GA digest; floating 1.19 has not moved past it.
#     PASS: 1.19.0 -> 200 sha256:daf5a6ae9d363ed578e7d41e2d0668c7eaa604bd90b0ff27435f893b0906833e,
#     1.19 SAME digest, 1.19.1 -> 404, isPrerelease false.
#     FAIL: 1.19.0 404 or a different digest (re-pushed tag: STOP), or 1.19 differs / 1.19.1 200
#     (a patch shipped): STOP and refresh this plan IN PLACE (keep plan_id) to the newest 1.19.N,
#     re-running the §1 prisma + package.json diff for v1.18.0..v1.19.N.
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:mintplexlabs/anythingllm:pull" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
for t in 1.19.0 1.19 1.19.1; do
  printf '%-8s ' "$t"
  curl -s -I -H "Authorization: Bearer $TOKEN" \
    -H "Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json" \
    "https://registry-1.docker.io/v2/mintplexlabs/anythingllm/manifests/$t" \
    | grep -i -E '^HTTP|docker-content-digest' | tr -d '\r' | tr '\n' ' '; echo
done
gh release view v1.19.0 -R Mintplex-Labs/anything-llm --json isPrerelease -q .isPrerelease   # PASS: false

# 2.2 PR #446 still open and unmerged (if it was merged, the premise live-image-still-1.18.0
#     will already have failed). PASS: OPEN
gh pr view 446 --json state -q .state

# 2.3 Last night's backup of the data volume COMPLETED (§5.3 source).
#     PASS: BACKUP_FRESH. BACKUP_STALE (>26h) or NO_BACKUP -> STOP.
kubectl get backups.longhorn.io -n storage -l backup-volume=pvc-b32f29a6-e7d3-49d7-879a-5c3808c6dadf -o json \
  | python3 -c "
import sys,json,datetime as d
b=[x for x in json.load(sys.stdin)['items'] if x.get('status',{}).get('state')=='Completed']
if not b: print('NO_BACKUP'); sys.exit(1)
t=max(x['status']['backupCreatedAt'] for x in b)
age=(d.datetime.now(d.timezone.utc)-d.datetime.fromisoformat(t.replace('Z','+00:00'))).total_seconds()/3600
print(('BACKUP_FRESH' if age<26 else 'BACKUP_STALE'), t, f'{age:.1f}h')"

# 2.4 Pod healthy, zero restarts, nothing in flight
kubectl get pods -n ai -l app.kubernetes.io/name=anythingllm \
  -o 'custom-columns=NAME:.metadata.name,PHASE:.status.phase,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount'
flux get kustomizations -n ai anythingllm
flux get helmreleases -n ai anythingllm
```

**2.5 Baseline CONTENTS census.** This is read-only: Prisma `count()`, a
LanceDB count plus vector search, and one unauthenticated local GET. Dry-run
live 2026-10-27 on 1.18.0 printed `workspaces=2 workspace_documents=293
workspace_chats=8 users=2 system_settings=5 prisma_migrations=40
lance_paperless=1241 lance_paperless_search_hits=3 api_vectordb=lancedb
api_llm=ollama api_multiuser=true`.

```bash
cat > /tmp/allm-census.js <<'EOF'
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

cat > /tmp/allm-compare.py <<'EOF'
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

P=$(kubectl -n ai get pod -l app.kubernetes.io/name=anythingllm -o jsonpath='{.items[0].metadata.name}')
kubectl -n ai exec -i "$P" -c anythingllm -- sh -c 'cd /app/server && node -' < /tmp/allm-census.js \
  | grep -v '^prisma:' > /tmp/allm-pre.txt
cat /tmp/allm-pre.txt
# PASS: no CENSUS_ERROR line, prisma_migrations=40, lance_paperless > 0, search_hits=3,
# api_multiuser=true. A different prisma_migrations means the baseline moved -> re-read §1.
grep -c -i -E '^(CENSUS_ERROR|lance_[a-z]+=0$)' /tmp/allm-pre.txt   # PASS: 0
```

## 3. Steps

**3.1 Silence + update marker** (application-update.md Step 1). The silence is
scoped to AnythingLLM's own pods. It is NOT namespace-wide, because other plans
(`python-fleet-3.15.0`, `redis-fleet-8.10.2`) roll workloads in `ai` and their
alerts must still fire.

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & PF=$!; sleep 2
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
for AN in 'AnythingLLM.*' 'KubePod.*|KubeContainer.*'; do
  curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
    "matchers":[{"name":"namespace","value":"ai","isRegex":false,"isEqual":true},
                {"name":"pod","value":"anythingllm-.*","isRegex":true,"isEqual":true},
                {"name":"alertname","value":"'"$AN"'","isRegex":true,"isEqual":true}],
    "startsAt":"'$NOW'","endsAt":"'$END'","createdBy":"maintenance-window-agent",
    "comment":"anythingllm 1.18.0->1.19.0 (plan anythingllm-1.19). auto-expires 2h"}'; echo
done
kill $PF 2>/dev/null
runbooks/update-marker.sh add anythingllm ai 2 "1.18.0->1.19.0 (plan anythingllm-1.19)"
```

**3.2 Off-cluster snapshot of the data** (the §5.2 restore source). A read-only
`tar` streamed to the Mac; nothing is written to the PVC.

```bash
P=$(kubectl -n ai get pod -l app.kubernetes.io/name=anythingllm -o jsonpath='{.items[0].metadata.name}')
SNAP=$HOME/anythingllm-pre-1.19.0-$(date +%Y%m%d_%H%M%S).tgz
kubectl -n ai exec "$P" -c anythingllm -- tar czf - -C /app/server/storage anythingllm.db lancedb > "$SNAP"
ls -l "$SNAP"; tar tzf "$SNAP" | grep -c -E '^(anythingllm\.db|lancedb/)'   # PASS: size > 1 MB AND count > 100
echo "$SNAP" > /tmp/allm-snap-path.txt
```

**3.3 Bump the pin.** Dry-tested 2026-10-27 with BSD sed on a scratch copy; the
result parses as YAML and `diff` printed exactly:

```bash
sed -i '' 's/tag: "1\.18\.0"/tag: "1.19.0@sha256:daf5a6ae9d363ed578e7d41e2d0668c7eaa604bd90b0ff27435f893b0906833e"/' \
  kubernetes/apps/ai/anythingllm/app/helmrelease.yaml
git diff kubernetes/apps/ai/anythingllm/app/helmrelease.yaml
# expected, exactly one hunk:
# -      tag: "1.18.0"
# +      tag: "1.19.0@sha256:daf5a6ae9d363ed578e7d41e2d0668c7eaa604bd90b0ff27435f893b0906833e"
```

**3.4 Commit + push** (shared-worktree rules: `--only`, then verify):

```bash
printf '%s\n\n%s\n' "chore(anythingllm): 1.18.0 -> 1.19.0 digest-pinned (plan anythingllm-1.19; supersedes #446)" \
  "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" > /tmp/allm-msg.txt
git commit --only kubernetes/apps/ai/anythingllm/app/helmrelease.yaml -F /tmp/allm-msg.txt
git log -1 --format=%s     # must be the subject above; amend before push if not
git show --stat HEAD       # exactly 1 file: kubernetes/apps/ai/anythingllm/app/helmrelease.yaml
git push
```

**3.5 Watch the rollout.** Flux picks the change up by webhook, so no manual
reconcile is needed. With Recreate, the old pod stops first. Then the init
container `clear-vector-cache` runs: it wipes only `vector-cache/` and
`comkey`, which is expected on every start. Then the new pod starts. Readiness
needs 2 successes 10 s apart on `:8888/v1/api/health`.

```bash
flux get helmreleases -n ai anythingllm      # wait until REVISION advances and READY True (<= 10 min)
kubectl get pods -n ai -l app.kubernetes.io/name=anythingllm \
  -o 'custom-columns=NAME:.metadata.name,PHASE:.status.phase,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount,IMAGE:.status.containerStatuses[0].imageID'
```
FAIL looks like: READY false with probe failures on 8888 in
`kubectl describe pod` (the collector bind changed despite §1), or
`ErrImagePull` (the digest is gone). In either case go to §5.1.

**3.6 Close the superseded Renovate PR** once §4 passes. It would otherwise sit
there as a second, digest-less route to the same bump. Renovate normally
auto-closes it on its next run when it sees the pin already at 1.19.0; this
step makes that deterministic.

```bash
gh pr view 446 --json state -q .state    # if still OPEN:
gh pr close 446 --comment "Landed digest-pinned via plan anythingllm-1.19 ($(git log -1 --format=%h -- kubernetes/apps/ai/anythingllm/app/helmrelease.yaml))."
```

## 4. Verification

Wait at least 5 minutes after the new pod is Ready before running 4.4. The
AnythingLLM alert rules use `for: 5m` / `for: 1m`.

**4.1 The running artifact is the pinned GA digest, not just the tag.**
`rollout status` can green-light the old generation, and a Helm remediation
rollback would leave git at 1.19.0 while the pod still runs 1.18.0.

```bash
P=$(kubectl -n ai get pod -l app.kubernetes.io/name=anythingllm -o jsonpath='{.items[0].metadata.name}')
kubectl -n ai get pod "$P" -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'
kubectl -n ai exec "$P" -c anythingllm -- printenv DEPLOYMENT_VERSION
```
PASS: imageID ends with
`sha256:daf5a6ae9d363ed578e7d41e2d0668c7eaa604bd90b0ff27435f893b0906833e`
AND `DEPLOYMENT_VERSION` prints `1.19.0`. The 1.18.0 pod reports the Hub index
digest today (`...@sha256:5461782e...` == Hub `1.18.0`), so the comparison
is like-for-like. FAIL looks like: `5461782e...` / `1.18.0` (the old pod or a
rollback).

**4.2 CONTENTS ASSERTION: same data, readable by 1.19.0, no migration ran.**

```bash
P=$(kubectl -n ai get pod -l app.kubernetes.io/name=anythingllm -o jsonpath='{.items[0].metadata.name}')
kubectl -n ai exec -i "$P" -c anythingllm -- sh -c 'cd /app/server && node -' < /tmp/allm-census.js \
  | grep -v '^prisma:' > /tmp/allm-post.txt
python3 /tmp/allm-compare.py /tmp/allm-pre.txt /tmp/allm-post.txt
```
PASS: `CENSUS_OK (11 keys identical)`, exit 0. `workspace_chats` may only
grow. Each key guards against a specific failure:
- `prisma_migrations` changed (e.g. `40->41`): a forward-only migration ran,
  so git revert alone is not a full rollback. Use §5.2.
- `MISSING lance_paperless`: LanceDB is unreadable or empty.
- `api_multiuser` / `api_vectordb` / `api_llm` changed: the server booted
  against fresh settings (for example, the built-in LLM took over as the
  provider). The census prints that state without erroring, which is why the
  values are compared.
- A `CENSUS_ERROR` line: Prisma or LanceDB cannot open the store.

Negative controls, run 2026-10-27 against the live 1.18.0 baseline:
- pre vs pre gives `CENSUS_OK (11 keys identical)`, rc 0.
- A tampered post (`prisma_migrations=41`, lance keys removed) gives
  `CENSUS_FAIL` with 3 reasons, rc 1.
- An empty pre file gives `CENSUS_FAIL` / `PRE census empty/errored`, rc 1.

**4.3 Serving path through the Gateway** (the user-facing route):

```bash
H=$(kubectl get httproute -n ai anythingllm -o jsonpath='{.spec.hostnames[0]}')
curl -s -o /dev/null -w '%{http_code}\n' "https://$H/api/ping"     # PASS: 200
curl -s "https://$H/api/ping"                                        # PASS: {"online":true}
```
FAIL looks like: 503 / `no healthy upstream` from Envoy, or any other body.

**4.4 Alert state after the soak, from Prometheus** (evaluated in Prometheus,
so the §3.1 silence does not hide it):

```bash
kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=ALERTS%7Balertname%3D~%22AnythingLLM.%2A%22%2Calertstate%3D%22firing%22%7D' \
  | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print('FIRING', [x['metric']['alertname'] for x in r]) if r else print('NONE_FIRING')"
kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=kube_deployment_status_replicas_available%7Bnamespace%3D%22ai%22%2Cdeployment%3D%22anythingllm%22%7D' \
  | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print('AVAIL', r[0]['value'][1] if r else 'ABSENT')"
```
PASS: `NONE_FIRING` AND `AVAIL 1`. `AVAIL ABSENT` is a FAIL: it means
kube-state-metrics or Prometheus is not answering, not that everything is fine.

CONTROL: metric kube_deployment_status_replicas_available — `{namespace="ai",deployment="anythingllm"}` must be 1; absent = FAIL.
CONTROL: metric kube_pod_container_status_restarts_total — `{namespace="ai",container="anythingllm"}` for the NEW pod must be 0 at T+5m.
CONTROL: alertname AnythingLLMPodCrashLooping — must NOT be firing at T+5m (rule in `kubernetes/apps/monitoring/kube-prometheus-stack/app/anythingllm-alerts.yaml`).
CONTROL: alertname AnythingLLMPodNotReady — must NOT be firing at T+5m (same rule file).
CONTROL: alertname AnythingLLMPodRestarted — must NOT be firing at T+5m (same rule file).

**4.5 Clean up and close out.** Delete the two §3.1 silences, or let them
expire after 2 h. Run `runbooks/update-marker.sh clear anythingllm`. Keep the
§3.2 tarball for 7 days. Close the version finding with the bump commit
(`policy-cli.py finding close F-2d0f09e2 --commit <sha>`). F-5af54d38 is
security-sweep-owned: confirm the next security scan no longer raises it on
1.18.0 before closing it. Then delete this plan file in the commit that
records `status: executed`.

## 5. Rollback

**5.1 Standard path: git revert** (enough whenever §4.2 shows `prisma_migrations=40`).

```bash
cd /Users/mu/code/cberg-home-nextgen
SHA=$(git log -1 --format=%H -- kubernetes/apps/ai/anythingllm/app/helmrelease.yaml)
git show --stat "$SHA"      # confirm it is the §3.4 bump commit
git revert --no-edit "$SHA"
git log -1 --format=%s      # must read: Revert "chore(anythingllm): 1.18.0 -> 1.19.0 digest-pinned ..."
git push
```
Confirm the cluster is back:
- The imageID ends in
  `sha256:5461782e7db41318a516925949a8f8366e258dd576411fca7961fe77dff054cc`.
- `DEPLOYMENT_VERSION` prints `1.18.0`. Use the same commands as §4.1.
- The §4.2 census against `/tmp/allm-pre.txt` prints `CENSUS_OK`.

If the HelmRelease is stuck (Ready=False, `upgrade retries exhausted`), note
that `maxHistory: 1` means `helm rollback` cannot reach the old revision.
Pushing the revert is still the fix. If the HR does not retry on its own, run
`flux reconcile helmrelease -n ai anythingllm --force` once
(application-update §6). Leave PR #446 closed. Renovate will reopen a fresh PR
on its own once the pin is 1.18.0 again.

**5.2 Data restore from the §3.2 tarball.** Use this only if §4.2 showed a
moved `prisma_migrations` or a missing/changed key, AND 1.18.0 still fails
against the current data after 5.1.

```bash
SNAP=$(cat /tmp/allm-snap-path.txt); ls -l "$SNAP"
P=$(kubectl -n ai get pod -l app.kubernetes.io/name=anythingllm -o jsonpath='{.items[0].metadata.name}')
# image must already be 1.18.0 (5.1 done). Move the current state aside on the PVC, then unpack:
kubectl -n ai exec "$P" -c anythingllm -- sh -c 'cd /app/server/storage && mv anythingllm.db anythingllm.db.failed-1.19.0 && mv lancedb lancedb.failed-1.19.0'
kubectl -n ai exec -i "$P" -c anythingllm -- tar xzf - -C /app/server/storage < "$SNAP"
kubectl -n ai delete pod "$P"     # Recreate -> a fresh 1.18.0 process opens the restored files
```
Confirm with the §4.2 census against `/tmp/allm-pre.txt`; it must print
`CENSUS_OK`. The `*.failed-1.19.0` copies stay on the PVC until the operator
says to delete them.

**5.3 Last resort: Longhorn backup.** Use this only if the tarball is
unusable. Restore the newest Completed backup of volume
`pvc-b32f29a6-e7d3-49d7-879a-5c3808c6dadf` that §2.3 confirmed, following
`docs/sops/backup.md` (restore to a new volume, then rebind the PV/PVC). This
must be operator-attended: the PVC is chart-created with a UUID PV, so the
rebind means editing the claim.

## 6. Interference notes

- **Outage:** about 1–2 min of the AnythingLLM UI/API (Recreate). No other
  in-cluster workload calls AnythingLLM.
- **Shared infra:** none is perturbed. The HTTPRoute on `envoy-internal` is
  unchanged. The Ollama host (192.168.30.111) gets only its normal startup
  calls, and no pinned model is touched. The built-in engine stays off:
  `ENABLE_BUILT_IN_LLM` is not set, and §4.2's `api_llm=ollama` would catch it
  if it took over.
- **Same namespace:** `python-fleet-3.15.0`, `redis-fleet-8.10.2`,
  `openclaw-2026.10.5` and `paperclip-26.04` touch other `ai` workloads. None
  of them shares a resource with this plan. The silence is pod-scoped.
- **Ordering:** run after the 03:00 Longhorn backup (§2.3 gates this). There
  are no `depends_on`.
- **Execution class:** HUMAN-GATED, because `capability_change: true` is
  decisive in `maintenance-plan.py execution_class()`. It is attended-window
  work that needs an operator GO, but it is low risk and fits any attended
  slot that is free of the four `conflicts_with` plans.
- **If upstream ships 1.19.N before the window:** §2.1 fails by design. Refresh
  in place (keep `plan_id`): re-run the §1 prisma/package diff and update the
  digests in the frontmatter, §2.1, §3.3, §4.1 and §5.1.
- **Repo correction (not acted on, carried over from the 1.17 plan):**
  `kubernetes/apps/ai/anythingllm/app/pvc.yaml` declares
  `pvc/anythingllm-storage`. It is not in the app's `kustomization.yaml` and
  does not exist live; the real claim is the chart-created
  `anythingllm-storage-claim`. Its UUID PV is also out of line with the
  speaking-name rule in `docs/sops/longhorn.md`. Fixing that is a separate
  migration plan.
