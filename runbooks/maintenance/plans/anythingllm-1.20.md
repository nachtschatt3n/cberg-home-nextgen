---
plan_id: anythingllm-1.20
component: anythingllm
pr: null                              # No Renovate PR exists yet (gh pr list 2026-11-18: none open for
                                      # anythingllm; #446 1.18.0->1.19.0 MERGED). v1.20.0 was published
                                      # 2026-11-17T20:38Z, so Renovate has not run against it yet.
                                      # When it opens "1.19.0 -> 1.20.0", §3.6 closes it as superseded.
kind: image
current: "1.19.0"                     # live 2026-11-18: deploy image mintplexlabs/anythingllm:1.19.0,
                                      # pod imageID ...@sha256:daf5a6ae9d36... (== Hub 1.19.0 == Hub 1.19),
                                      # DEPLOYMENT_VERSION=1.19.0, node 18, @lancedb/lancedb 0.15.0.
target: "1.20.0@sha256:3e2b7bc8eb0f73a130fc575f1372bd4e7189e399a63c037497fc183c141fc0ae"
                                      # fixed GA tag replacing the floating `1.20` the sweep reported.
                                      # Hub 2026-11-18: 1.20 == 1.20.0 == sha256:3e2b7bc8... (OCI index,
                                      # linux/amd64 + arm64); 1.20.1/1.20.2/1.21.0 -> 404; `latest` has
                                      # ALREADY moved past it to a master build (sha256:714f62ea...).
                                      # GitHub v1.20.0 isPrerelease=false, "Latest".
update_type: minor
risk: medium                          # NOT low, unlike 1.19: the image switches the runtime Node 18 -> 24
                                      # (#6893) AND bumps the only vector store's engine @lancedb/lancedb
                                      # 0.15.0 -> 0.30.0 (#7093). 0 prisma migrations (§1). Single internal
                                      # app, own PVC, small re-embeddable data, Recreate, local tarball +
                                      # nightly Longhorn backup — but LanceDB writes after the bump are not
                                      # proven readable by 0.15 (§1, §5).
est_duration_min: 35
needs_reboot: false
touches:
  namespaces: [ai]
  resources:
    - helmrelease/anythingllm         # values.image.tag edit (the only file change)
    - deployment/anythingllm          # Recreate -> ~1-2 min outage of the RAG UI/API
    - pvc/anythingllm-storage-claim   # NOT edited; re-mounted (Longhorn dynamic PV
                                      # pvc-b32f29a6-e7d3-49d7-879a-5c3808c6dadf, RWO); LanceDB files
                                      # on it are opened by lancedb 0.30 from now on.
  shared: []                          # HTTPRoute (envoy-internal) untouched; no shared DB (own SQLite +
                                      # LanceDB); the Ollama host 192.168.30.111 is only called, not
                                      # changed; Longhorn: a re-attach, no volume operation. §4.4 READS
                                      # Prometheus (hence kube-prometheus-stack in conflicts_with).
depends_on: []
conflicts_with: [flux-oci-chart-sources, helm-drift-detection, longhorn-1.13.0, kube-prometheus-stack-93.3.0, flux-reconciler-impersonation]
                                      # flux-oci-chart-sources: re-points the mintplex-labs HelmRepository
                                      #   serving this HR's chart and ROLLS deployment/anythingllm in its
                                      #   stage 5 (vetted, sun-attended:2026-12-13).
                                      # helm-drift-detection: adds driftDetection to every HR incl.
                                      #   ai/anythingllm and gates on "no Helm upgrade happened" — this plan
                                      #   IS a Helm upgrade of that HR (vetted, sat-attended:2026-11-28).
                                      # longhorn-1.13.0: storage-engine upgrade; this plan re-attaches a
                                      #   Longhorn volume and §5.3 restores from Longhorn (sun 2026-11-22).
                                      # kube-prometheus-stack-93.3.0: §4.4 reads Prometheus/ALERTS (draft).
                                      # flux-reconciler-impersonation: new reconciler SA for ns ai (blocked).
                                      # Every other open plan's frontmatter checked 2026-11-18; the
                                      # anythingllm-1.19 plan is stale (already applied via #446, see §6).
exclusive: false
security_ref: null                    # dispatcher: no security evidence for this target. The AR-029
                                      # register rows on the 1.19.0 image are security-sweep-owned; the
                                      # next scan after this bump re-evaluates them (§4.5).
finding_refs: [F-2d0f09e2]
                                      # F-2d0f09e2 = the recurring anythingllm version finding (same id
                                      # carried "1.16.2 -> 1.17", "1.17.0 -> 1.18", "1.18.0 -> 1.19"; it
                                      # reads resolved at 2026-10-27 and is re-raised for "1.19.0 -> 1.20"
                                      # by sweep cycle fa131284). `finding list --grep anythingllm --all`
                                      # 2026-11-18 shows no other version/plan-lane row for 1.20.
capability_change: true               # TRUTHFUL: v1.20.0 adds a new developer API (`/v1/mcp-servers`
                                      # list/add/update/delete/start/stop, #7037), MCP identity forwarding
                                      # (#7038), a chat-capable browser-extension sidebar, email approval
                                      # cards, DeepSeek agent web search; and changes behaviour: the
                                      # container runtime is Node 24 (#6893), user deletion now keeps
                                      # workspace chats (#6913), concurrent Paperless-ngx downloads capped
                                      # (#7096), empty-vector rows rejected on LanceDB insert (#7093).
rollback_class: backup-restore        # 0 prisma migrations (git diff v1.19.0..v1.20.0 -- server/prisma is
                                      # empty), so the SQLite side reverts with git. But LanceDB 0.30 may
                                      # write table versions/fragments that lancedb 0.15 cannot read; this
                                      # is NOT proven either way. Any write after the bump (an embed, a
                                      # document removal) can therefore make `git revert` incomplete —
                                      # §5.1 tests it with the census, §5.2 restores the §3.2 tarball.
review: null
status: draft
window: null
premises:
  - id: live-image-still-1.19.0
    why: >-
      `current:` and the rollback target claim 1.19.0. If the Deployment already
      moved (a merged Renovate PR or the Step-0 lane), baseline and revert target are wrong.
    run: kubectl get deploy -n ai anythingllm -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: mintplexlabs/anythingllm:1.19.0
  - id: manifest-pin-still-1.19.0
    why: "§3.3's sed anchors on the exact string `tag: \"1.19.0\"`; a changed pin makes it a silent no-op."
    run: grep -c 'tag. "1.19.0"' /Users/mu/code/cberg-home-nextgen/kubernetes/apps/ai/anythingllm/app/helmrelease.yaml
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
  - id: running-pod-is-1.19.0-digest
    why: >-
      §1's forward-compat reasoning (lancedb 0.15 -> 0.30, Node 18 -> 24) and the §5.1 "old
      reader" test assume the running pod is the 1.19.0 image, measured 2026-11-18 to ship
      lancedb 0.15.0 on Node 18 (§2.4b re-measures it in-pod). Another digest means §1 must be re-read.
    run: kubectl get pod -n ai -l app.kubernetes.io/name=anythingllm -o jsonpath='{.items[0].status.containerStatuses[0].imageID}'
    expect_matches: 'sha256:daf5a6ae9d363ed578e7d41e2d0668c7eaa604bd90b0ff27435f893b0906833e$'
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/longhorn.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/backup.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-11-18"
---

# anythingllm: 1.19.0 -> 1.20.0 (digest-pinned GA for the floating `1.20`)

## 1. Summary & why held

AnythingLLM (namespace `ai`, Mintplex chart `anythingllm` 1.0.0, image
`mintplexlabs/anythingllm`) is the internal multi-user RAG workspace, routed
only on `envoy-internal`. Its state is one RWO Longhorn PVC
`anythingllm-storage-claim` (chart-created, dynamic PV `pvc-b32f29a6-...`) at
`/app/server/storage`: Prisma/SQLite `anythingllm.db` (916 KB), LanceDB
`lancedb/paperless.lance` (13 MB, 1241 vectors), `documents/` (2.5 MB). The
LLM and embeddings run on the shared Ollama host, which this plan does not touch.

**Why held, and how it resolves.** The sweep's target was `1.20`. That has fewer
components than the pinned `1.19.0`, so it is a floating series pointer
(`coverage.py` floating-target guard). **A fixed GA tag exists.** Measured
2026-11-18 with a registry-1 manifest HEAD (OCI index digest), the Hub tag API
and GitHub:

| Probe | Result |
|---|---|
| `mintplexlabs/anythingllm:1.20.0` | 200, `sha256:3e2b7bc8eb0f73a1...` (pushed 2026-11-17T20:40:51Z; index has linux/amd64 + arm64) |
| `:1.20` | 200, **same** `sha256:3e2b7bc8...` |
| `:1.20.1`, `:1.20.2`, `:1.21.0` | 404 |
| `:latest` / `:master` | 200, `sha256:714f62ea...`: a later master build, **not** 1.20.0 |
| `:1.19.0` / `:1.19` | 200, `sha256:daf5a6ae...` (== the running pod's imageID) |
| GitHub `v1.20.0` | published 2026-11-17T20:38Z, `isPrerelease=false`, **Latest** |

This plan pins `1.20.0@sha256:3e2b7bc8...`. The floating `1.20` is never
written. `helm template oci://ghcr.io/mintplex-labs/helm-charts/anythingllm
--version 1.0.0` with that tag renders
`image: "mintplexlabs/anythingllm:1.20.0@sha256:3e2b7bc8eb0f73a130fc575f1372bd4e7189e399a63c037497fc183c141fc0ae"`
(verified 2026-11-18).

**Should Renovate be steered away from the floating tag? No.** Renovate is not
where the floating target comes from. It has opened no PR for 1.20 yet, and its
docker versioning only proposes tags with the same number of components as the
current pin, so it will propose `1.19.0 -> 1.20.0`. The floating `1.20` comes
from the sweep's `runbooks/check-all-versions.py`. It has now reported a
two-component target for this image four releases in a row (1.17, 1.18, 1.19,
1.20 on F-2d0f09e2), and each time a planner had to resolve it by hand. That is
a repo correction (see §6), not a Renovate rule.

**Release notes v1.20.0.** There is no "breaking" or "migration" section.
Headline features: the browser-extension chat sidebar, a rebuilt PowerPoint
tool, Gmail/Outlook email approval cards, and MCP identity forwarding,
per-server timeouts and a `/v1/mcp-servers` developer API. There are about 120
fixes. Two of the changes are why this plan is `risk: medium`, not low as 1.19
was:

- **#6893 "Chore/Maint: Bump Node from 18 to 24 LTS"**. `docker/Dockerfile`
  now installs `node_24.x` from nodesource in both runtime stages, and the
  frontend builds on `node:24-slim`. The live pod runs Node 18 today. A
  runtime major jump inside the same image tag line can surface as a boot
  crash (native module ABI), a different heap ceiling against our 2Gi limit
  (OOMKilled), or a probe failure. §3.5 and §4.1/§4.4 gate all three.
- **#7093 "fix: bump lancedb to 0.30.0 and reject empty vectors before
  insert"**. `server/package.json`: `"@lancedb/lancedb": "0.15.0"` ->
  `"0.30.0"`. That is the only dependency change in `server/` and
  `collector/`; `@prisma/client` is unchanged. The commit says *"Rows with an
  empty vector made LanceDB 0.15.0 create a table with a 0-dimension vector
  column. Every later read of that table panicked ... It refuses to create a
  0-dim table, and a panic on an existing one comes back as a catchable JS
  error."* Our only table, `paperless`, has 1241 real vectors and
  answers a 3-hit search today (§2.5 baseline), so it is not the degenerate
  case. Upstream ships no migration step and no format note. **Unproven:**
  whether a table that lancedb 0.30 has *written* to is still readable by
  0.15. That is why `rollback_class: backup-restore` and §5.1 test the old
  reader explicitly.

Other changes that touch our wiring, each checked in the v1.19.0..v1.20.0 diff
(full clone; 351 files changed):

- **#7096 "cap concurrent Paperless-ngx document downloads"**
  (`collector/utils/extensions/PaperlessNgx/...`). This is the connector that
  fed our `paperless` workspace. It changes throughput only, not stored data.
- **#6908 "filter ineligible Lance candidates before reranking"**
  (`server/utils/vectorDbProviders/lance/index.js`). The threshold and pinned
  filters now run before the reranker. Retrieval results can differ slightly
  (more relevant results fill the topN slots). This is behaviour, not data.
- **#6944 "serve the dynamic PWA manifest before static files"**
  (`server/index.js`: the `/manifest.json` route moved up). Our probes hit the
  collector `:8888/v1/api/health`, and §4.3 hits `/api/ping`; neither is
  affected.
- **#6912 `DISABLE_METRICS_ENDPOINT`**: a new opt-out for the
  already-existing unauthenticated `/api/utils/metrics`. The default is
  unchanged, so this is not a new exposure, and the route is LAN-only.
- `docker/.env.example` only changes commented defaults. The entrypoint is
  unchanged. `DEPLOYMENT_VERSION=1.20.0`.

**Data store evidence** (this decides `rollback_class`):
`git diff --name-status v1.19.0 v1.20.0 -- server/prisma` is **empty**: no
schema change and no new migration. The live baseline `_prisma_migrations` is
40 finished rows (unchanged since 1.16.2). The SQLite side is therefore
reverted by `git revert`. The LanceDB side is covered by the §3.2 tarball.

## 2. Pre-checks

Run from `/Users/mu/code/cberg-home-nextgen` in zsh. The nightly
`storage/daily-backup-all-volumes` CronJob (`0 23 * * *` UTC; last success
2026-11-17T23:09Z) must have finished; every window starts after it.

```bash
cd /Users/mu/code/cberg-home-nextgen

# 2.0 Premises (all six must PASS)
.venv/bin/python3 runbooks/plan-premises.py anythingllm-1.20 --require-premises

# 2.1 Target is still the GA digest; the floating 1.20 has not moved past it.
#     PASS: 1.20.0 -> 200 sha256:3e2b7bc8eb0f73a130fc575f1372bd4e7189e399a63c037497fc183c141fc0ae,
#     1.20 SAME digest, 1.20.1 -> 404, isPrerelease false.
#     FAIL: 1.20.0 404 or a different digest (re-pushed tag: STOP), or 1.20 differs / 1.20.1 200
#     (a patch shipped): STOP and refresh this plan IN PLACE (keep plan_id) to the newest 1.20.N,
#     re-running the §1 prisma + package.json diff for v1.19.0..v1.20.N.
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:mintplexlabs/anythingllm:pull" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
for t in 1.20.0 1.20 1.20.1; do
  printf '%-8s ' "$t"
  curl -s -I -H "Authorization: Bearer $TOKEN" \
    -H "Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json" \
    "https://registry-1.docker.io/v2/mintplexlabs/anythingllm/manifests/$t" \
    | grep -i -E '^HTTP|docker-content-digest' | tr -d '\r' | tr '\n' ' '; echo
done
gh release view v1.20.0 -R Mintplex-Labs/anything-llm --json isPrerelease -q .isPrerelease   # PASS: false

# 2.2 Renovate PR state (informational; decides §3.6). Prints the PR number if Renovate has
#     opened "1.19.0 -> 1.20.0" since 2026-11-18; empty = none yet.
gh pr list --state open --search "mintplexlabs/anythingllm in:title" --json number,title -q '.[] | "\(.number) \(.title)"'

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

# 2.4 Pod healthy, nothing in flight. (restartCount was 2 on 2026-11-18, last exit 255 "Unknown"
#     at 2026-11-12T13:30Z = node event, not app crash; record the number, §4.4 compares the NEW pod.)
kubectl get pods -n ai -l app.kubernetes.io/name=anythingllm \
  -o 'custom-columns=NAME:.metadata.name,PHASE:.status.phase,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount'
flux get kustomizations -n ai anythingllm
flux get helmreleases -n ai anythingllm

# 2.4b Runtime baseline in-pod (the premise checks the digest; this checks what it ships).
#      PASS: "18 0.15.0". Anything else: the baseline moved, re-read §1 before rolling.
P=$(kubectl -n ai get pod -l app.kubernetes.io/name=anythingllm -o jsonpath='{.items[0].metadata.name}')
kubectl -n ai exec "$P" -c anythingllm -- node -p "process.versions.node.split('.')[0] + ' ' + require('/app/server/node_modules/@lancedb/lancedb/package.json').version"
```

**2.5 Baseline CONTENTS census.** This is read-only: Prisma `count()`, a
LanceDB row count plus a vector search, and one unauthenticated local GET.
The script uses only lancedb APIs that exist in both 0.15 and 0.30
(`connect`, `tableNames`, `openTable`, `countRows`, `query().limit()`,
`search().limit()`). Dry-run live on 1.19.0 on 2026-11-18, it printed
`workspaces=2 workspace_documents=293 workspace_chats=8 users=2
system_settings=5 prisma_migrations=40 lance_paperless=1241
lance_paperless_search_hits=3 api_vectordb=lancedb api_llm=ollama
api_multiuser=true`.

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
# api_multiuser=true. A different prisma_migrations means the baseline moved: re-read §1.
grep -c -i -E '^(CENSUS_ERROR|lance_[a-z]+=0$)' /tmp/allm-pre.txt   # PASS: 0
```

## 3. Steps

**3.1 Silence + update marker** (application-update.md Step 1). The silence is
scoped to AnythingLLM's own pods, not the whole namespace, so alerts from other
`ai` workloads still fire.

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
    "comment":"anythingllm 1.19.0->1.20.0 (plan anythingllm-1.20). auto-expires 2h"}'; echo
done
kill $PF 2>/dev/null
runbooks/update-marker.sh add anythingllm ai 2 "1.19.0->1.20.0 (plan anythingllm-1.20)"
```

**3.2 Off-cluster snapshot of the data** (the §5.2 restore source, and the
reason `rollback_class` is `backup-restore`). A read-only `tar` streamed to
the Mac; nothing is written to the PVC. There is no `-wal`/`-journal` file
next to `anythingllm.db` (listed 2026-11-18), so a hot copy of the idle
SQLite file is consistent. Run it at a quiet moment (no chat in flight).

```bash
P=$(kubectl -n ai get pod -l app.kubernetes.io/name=anythingllm -o jsonpath='{.items[0].metadata.name}')
SNAP=$HOME/anythingllm-pre-1.20.0-$(date +%Y%m%d_%H%M%S).tgz
kubectl -n ai exec "$P" -c anythingllm -- tar czf - -C /app/server/storage anythingllm.db lancedb documents plugins > "$SNAP"
ls -l "$SNAP"; tar tzf "$SNAP" | grep -c -E '^(anythingllm\.db|lancedb/)'   # PASS: size > 1 MB AND count > 100
echo "$SNAP" > /tmp/allm-snap-path.txt
```

**3.3 Bump the pin.** Dry-tested 2026-11-18 with BSD sed on a scratch copy of
`helmrelease.yaml`. The result parses as YAML (`values.image.tag` ==
`1.20.0@sha256:3e2b...`), and `diff` printed exactly:

```bash
sed -i '' 's/tag: "1\.19\.0"/tag: "1.20.0@sha256:3e2b7bc8eb0f73a130fc575f1372bd4e7189e399a63c037497fc183c141fc0ae"/' \
  kubernetes/apps/ai/anythingllm/app/helmrelease.yaml
git diff kubernetes/apps/ai/anythingllm/app/helmrelease.yaml
# expected, exactly one hunk (dry-run output):
# 101c101
# <       tag: "1.19.0"
# ---
# >       tag: "1.20.0@sha256:3e2b7bc8eb0f73a130fc575f1372bd4e7189e399a63c037497fc183c141fc0ae"
```

**3.4 Commit + push** (shared-worktree rules: use `--only`, then verify):

```bash
printf '%s\n\n%s\n' "chore(anythingllm): 1.19.0 -> 1.20.0 digest-pinned (plan anythingllm-1.20)" \
  "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" > /tmp/allm-msg.txt
git commit --only kubernetes/apps/ai/anythingllm/app/helmrelease.yaml -F /tmp/allm-msg.txt
git log -1 --format=%s     # must be the subject above; amend before push if not
git show --stat HEAD       # exactly 1 file: kubernetes/apps/ai/anythingllm/app/helmrelease.yaml
git push
```

**3.5 Watch the rollout.** Flux picks the change up by webhook, so no manual
reconcile is needed. With Recreate, the old pod stops first. Then the init
container `clear-vector-cache` runs (it wipes only `vector-cache/` and
`comkey`, which is expected on every start). Then the Node 24 process starts.
Readiness needs 2 successes 10 s apart on `:8888/v1/api/health`.

```bash
flux get helmreleases -n ai anythingllm      # wait until REVISION advances and READY True (<= 10 min)
kubectl get pods -n ai -l app.kubernetes.io/name=anythingllm \
  -o 'custom-columns=NAME:.metadata.name,PHASE:.status.phase,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount,LAST:.status.containerStatuses[0].lastState.terminated.reason,IMAGE:.status.containerStatuses[0].imageID'
```
What a failure looks like:
- `LAST` = `OOMKilled`: the Node 24 heap does not fit the 2Gi limit.
- `CrashLoopBackOff`, with `kubectl logs -n ai deploy/anythingllm -c anythingllm --previous` showing a native-module / `ERR_DLOPEN_FAILED` / lancedb panic.
- READY false with probe failures on 8888.
- `ErrImagePull`: the digest is gone.

In any of these cases go to §5.1. Do not tune the limits in the window.

**3.6 Close the Renovate PR, if one was opened** (§2.2). Once §4 passes, a
Renovate `1.19.0 -> 1.20.0` PR is a second, digest-less route to the same
bump. Renovate normally auto-closes it on its next run once the pin reads
1.20.0. This step makes that deterministic.

```bash
N=$(gh pr list --state open --search "mintplexlabs/anythingllm in:title" --json number -q '.[0].number')
[ -n "$N" ] && gh pr close "$N" --comment "Landed digest-pinned via plan anythingllm-1.20 ($(git log -1 --format=%h -- kubernetes/apps/ai/anythingllm/app/helmrelease.yaml))."
```

## 4. Verification

Wait at least 5 minutes after the new pod is Ready before running 4.4. The
AnythingLLM alert rules use `for: 5m` / `for: 1m`.

**4.1 The running artifact is the pinned GA digest on the new runtime.**
`rollout status` can green-light the old generation, and a Helm remediation
rollback would leave git at 1.20.0 while the pod still runs 1.19.0.

```bash
P=$(kubectl -n ai get pod -l app.kubernetes.io/name=anythingllm -o jsonpath='{.items[0].metadata.name}')
kubectl -n ai get pod "$P" -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'
kubectl -n ai exec "$P" -c anythingllm -- printenv DEPLOYMENT_VERSION
kubectl -n ai exec "$P" -c anythingllm -- node -p "process.versions.node.split('.')[0] + ' ' + require('/app/server/node_modules/@lancedb/lancedb/package.json').version"
```
PASS requires all three:
- imageID ends with `sha256:3e2b7bc8eb0f73a130fc575f1372bd4e7189e399a63c037497fc183c141fc0ae`.
- `DEPLOYMENT_VERSION` prints `1.20.0`.
- The last line prints `24 0.30.0`.

The 1.19.0 pod reports the Hub index digest today
(`...@sha256:daf5a6ae...` == Hub `1.19.0`), so the digest comparison is
like-for-like. What a failure looks like: `daf5a6ae...` / `1.19.0` /
`18 0.15.0`, which means the old pod or a rollback.

**4.2 CONTENTS ASSERTION: same data, readable by lancedb 0.30, no migration ran.**

```bash
P=$(kubectl -n ai get pod -l app.kubernetes.io/name=anythingllm -o jsonpath='{.items[0].metadata.name}')
kubectl -n ai exec -i "$P" -c anythingllm -- sh -c 'cd /app/server && node -' < /tmp/allm-census.js \
  | grep -v '^prisma:' > /tmp/allm-post.txt
python3 /tmp/allm-compare.py /tmp/allm-pre.txt /tmp/allm-post.txt
```
PASS: `CENSUS_OK (11 keys identical)`, exit 0. `workspace_chats` may only
grow. Each key guards against a specific failure:
- `prisma_migrations` changed (e.g. `40->41`): a forward-only migration ran
  that §1 did not find. Treat rollback as §5.2.
- `MISSING lance_paperless`, `lance_paperless` changed, `search_hits` not 3,
  or a `CENSUS_ERROR` naming lance: lancedb 0.30 cannot open or search the
  0.15-written table. This is the #7093 risk. Go to §5.1 now, before any
  write happens.
- `api_multiuser` / `api_vectordb` / `api_llm` changed: the server booted
  against fresh settings. The census prints that state without erroring,
  which is why the values are compared.

The negative controls for this compare script were run 2026-10-27 (same script, 1.19 plan):
- pre vs pre gives `CENSUS_OK`, rc 0.
- A tampered post (`prisma_migrations=41`, lance keys removed) gives
  `CENSUS_FAIL` with 3 reasons, rc 1.
- An empty pre file gives `CENSUS_FAIL` / `PRE census empty/errored`, rc 1.

Today's live baseline confirms the census still runs end-to-end on 1.19.0.

**4.3 Serving path through the Gateway** (the user-facing route; probed
2026-11-18 on 1.19.0: `{"online":true}`):

```bash
H=$(kubectl get httproute -n ai anythingllm -o jsonpath='{.spec.hostnames[0]}')
curl -s -o /dev/null -w '%{http_code}\n' "https://$H/api/ping"     # PASS: 200
curl -s "https://$H/api/ping"                                        # PASS: {"online":true}
```
What a failure looks like: 503 / `no healthy upstream` from Envoy, or any
other body.

**4.4 Alert state and restarts after the 5-minute soak, from Prometheus.**
These are evaluated in Prometheus, so the §3.1 silence does not hide them.

```bash
kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=ALERTS%7Balertname%3D~%22AnythingLLM.%2A%22%2Calertstate%3D%22firing%22%7D' \
  | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print('FIRING', [x['metric']['alertname'] for x in r]) if r else print('NONE_FIRING')"
kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=kube_deployment_status_replicas_available%7Bnamespace%3D%22ai%22%2Cdeployment%3D%22anythingllm%22%7D' \
  | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print('AVAIL', r[0]['value'][1] if r else 'ABSENT')"
kubectl get pods -n ai -l app.kubernetes.io/name=anythingllm -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}{"\n"}'
```
PASS requires all three:
- `NONE_FIRING`.
- `AVAIL 1`. The series was answered live on 2026-11-18. `AVAIL ABSENT`
  counts as a FAIL: it means kube-state-metrics or Prometheus is not
  answering, not that everything is fine.
- The new pod's restartCount is `0`. A `1` here at T+5m is the Node 24 OOM or
  crash signature that §3.5 can miss.

CONTROL: metric kube_deployment_status_replicas_available — `{namespace="ai",deployment="anythingllm"}` must be 1; absent = FAIL.
CONTROL: metric kube_pod_container_status_restarts_total — `{namespace="ai",container="anythingllm"}` for the NEW pod must be 0 at T+5m.
CONTROL: alertname AnythingLLMPodCrashLooping — must NOT be firing at T+5m (rule in `kubernetes/apps/monitoring/kube-prometheus-stack/app/anythingllm-alerts.yaml`).
CONTROL: alertname AnythingLLMPodNotReady — must NOT be firing at T+5m (same rule file).
CONTROL: alertname AnythingLLMPodRestarted — must NOT be firing at T+5m (same rule file).

**4.5 Clean up and close out.**
- Delete the two §3.1 silences, or let them expire after 2 h.
- Run `runbooks/update-marker.sh clear anythingllm`.
- Keep the §3.2 tarball for 7 days. After any LanceDB write under 1.20.0 it
  is the only clean 0.15-readable copy.
- Close the version finding with the bump commit:
  `policy-cli.py finding close F-2d0f09e2 --commit <sha>`.
- The AR-029 rows on `mintplexlabs/anythingllm:1.19.0` are security-sweep-owned.
  Let the next security scan re-evaluate the 1.20.0 image rather than closing
  them by hand.
- Set `status: executed` in this plan.

## 5. Rollback

**5.1 Standard path: git revert, then PROVE the old reader still works.**

```bash
cd /Users/mu/code/cberg-home-nextgen
SHA=$(git log -1 --format=%H -- kubernetes/apps/ai/anythingllm/app/helmrelease.yaml)
git show --stat "$SHA"      # confirm it is the §3.4 bump commit
git revert --no-edit "$SHA"
git log -1 --format=%s      # must read: Revert "chore(anythingllm): 1.19.0 -> 1.20.0 digest-pinned ..."
git push
```
Confirm the cluster is back:
- The imageID ends in
  `sha256:daf5a6ae9d363ed578e7d41e2d0668c7eaa604bd90b0ff27435f893b0906833e`.
- The §4.1 runtime line prints `18 0.15.0`.
- **The §4.2 census, run on 1.19.0 against `/tmp/allm-pre.txt`, prints
  `CENSUS_OK`.** This is the test that the 0.15 reader can still open what
  0.30 left on disk. A `CENSUS_ERROR` naming lance, or a changed `lance_*`
  key, means 0.30 wrote something 0.15 cannot read. Go to §5.2.

If the HelmRelease is stuck (Ready=False, `upgrade retries exhausted`), note
that `maxHistory: 1` means `helm rollback` cannot reach the old revision.
Pushing the revert is still the fix. If the HR does not retry on its own, run
`flux reconcile helmrelease -n ai anythingllm --force` once
(application-update §6).

**5.2 Data restore from the §3.2 tarball.** Use this when the §5.1 census
fails, or §4.2 showed a moved `prisma_migrations`. It loses any chats or
embeds made under 1.20.0. The image must already be 1.19.0 (5.1 done).

```bash
SNAP=$(cat /tmp/allm-snap-path.txt); ls -l "$SNAP"
P=$(kubectl -n ai get pod -l app.kubernetes.io/name=anythingllm -o jsonpath='{.items[0].metadata.name}')
# Move the current state aside on the PVC (kept, not deleted), then unpack:
kubectl -n ai exec "$P" -c anythingllm -- sh -c 'cd /app/server/storage && mv anythingllm.db anythingllm.db.failed-1.20.0 && mv lancedb lancedb.failed-1.20.0 && mv documents documents.failed-1.20.0 && mv plugins plugins.failed-1.20.0'
kubectl -n ai exec -i "$P" -c anythingllm -- tar xzf - -C /app/server/storage < "$SNAP"
kubectl -n ai delete pod "$P"     # Recreate -> a fresh 1.19.0 process opens the restored files
```
Confirm with the §4.2 census against `/tmp/allm-pre.txt`. It must print
`CENSUS_OK`. The `*.failed-1.20.0` copies stay on the PVC until the operator
says to delete them.

**5.3 Last resort: Longhorn backup.** Use this only if the tarball is
unusable. Restore the newest Completed backup of volume
`pvc-b32f29a6-e7d3-49d7-879a-5c3808c6dadf` that §2.3 confirmed, following
`docs/sops/backup.md` (restore to a new volume, then rebind the PV/PVC). This
must be operator-attended: the PVC is chart-created with a UUID PV, so the
rebind means editing the claim. Fallback of the fallback: the `paperless`
LanceDB table is derived data. It can be re-embedded from Paperless through
the connector; that is slow but loses nothing authoritative.

## 6. Interference notes

- **Outage:** about 1–2 min of the AnythingLLM UI/API (Recreate). No other
  in-cluster workload calls AnythingLLM.
- **Shared infra:** none is perturbed. The HTTPRoute on `envoy-internal` is
  unchanged. The Ollama host (192.168.30.111) gets only its normal startup
  and model-list calls, and no pinned model is touched. `ENABLE_BUILT_IN_LLM`
  is still unset, and §4.2's `api_llm=ollama` would catch a provider switch.
- **Same namespace:** other `ai` workloads (openclaw, open-webui, paperclip,
  oc8) share no resource with this plan. The silence is pod-scoped.
- **Ordering:** run after the 23:00 UTC Longhorn backup (§2.3 gates this).
  There are no `depends_on`. Do not share a window with any of the five
  `conflicts_with` plans: flux-oci-chart-sources rolls this exact Deployment
  in stage 5, and helm-drift-detection asserts that no Helm upgrade happened
  on this HR.
- **Execution class:** HUMAN-GATED. `capability_change: true` and
  `rollback_class: backup-restore` without a `backup_gate` are each decisive.
  This is attended-window work that needs an operator GO. It is medium risk
  and fits any free sat/sun attended slot.
- **No write in the soak.** Between §3.5 and the end of §4, do not embed or
  remove documents. This keeps the §5.1 "old reader" test meaningful and the
  tarball current. After §4 passes, normal use resumes.
- **If upstream ships 1.20.N before the window:** §2.1 fails by design.
  Refresh this plan in place (keep `plan_id`): re-run the §1 prisma/package
  diff and update the digests in the frontmatter, §2.1, §3.3, §4.1 and §5.1.
- **Repo corrections (not acted on; for the sweep/operator):**
  1. `runbooks/check-all-versions.py` reports a two-component floating target
     (`1.20`) for `mintplexlabs/anythingllm` when the same digest is published
     as `1.20.0`. This is the fourth release in a row on F-2d0f09e2. Fix: when
     the newest tag has fewer components than the pin, resolve it to the
     same-digest tag that matches the pin's component count, before emitting.
     That would also clear the `coverage.py` floating-target hold for this
     image. Renovate needs no rule change.
  2. `runbooks/maintenance/plans/anythingllm-1.19.md` is still `status: draft`.
     The 1.19.0 bump landed through Renovate PR #446 (merged; live image
     1.19.0 without a digest), and F-4e9b4d10 already flags it as superseded.
     It should be marked `superseded`. It is still named in other plans'
     `conflicts_with` (flux-oci-chart-sources, longhorn-1.13.0,
     kube-prometheus-stack-93.3.0); those should point at this plan instead.
  3. (Carried from the 1.17/1.19 plans.)
     `kubernetes/apps/ai/anythingllm/app/pvc.yaml` declares
     `pvc/anythingllm-storage`. It is not in the app's `kustomization.yaml`
     and does not exist live; the real claim is the chart-created
     `anythingllm-storage-claim`, on a UUID PV that breaks the speaking-name
     rule. Fixing that is a separate migration plan.
