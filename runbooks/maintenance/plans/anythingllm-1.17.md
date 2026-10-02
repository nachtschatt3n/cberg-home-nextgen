---
plan_id: anythingllm-1.17
component: anythingllm
pr: null                              # no Renovate PR; coverage.py routed the floating `1.17` to PLAN
kind: image
current: "1.16.2"                     # live-verified 2026-10-02: deploy image mintplexlabs/anythingllm:1.16.2,
                                      # pod imageID digest sha256:480b0f10... (== Hub 1.16.2 == Hub 1.16)
target: "1.17.0 (fixed GA pin replacing the floating 1.17)"
                                      # Hub 2026-10-02: 1.17 == 1.17.0 == latest, index digest
                                      # sha256:f26f30df46916b6e953e3a47ca98f48817726e3df635e62d4bfdd133292ecfff;
                                      # 1.17.1/1.17.2/1.17.3 -> 404. GitHub v1.17.0 isPrerelease=false, "Latest".
                                      # Pin the FIXED tag 1.17.0, never the floating 1.17.
update_type: minor
risk: low                             # single-user internal RAG app, no schema migration between
                                      # v1.16.2..v1.17.0 (0 prisma files changed, 0 dependency bumps —
                                      # §1), Recreate strategy, local tarball + nightly Longhorn backup.
est_duration_min: 25
needs_reboot: false
touches:
  namespaces: [ai]
  resources:
    - helmrelease/anythingllm         # values.image.tag edit (the only file change)
    - deployment/anythingllm          # Recreate -> ~1-2 min outage of the RAG UI/API
    - pvc/anythingllm-storage-claim   # NOT edited; the new pod mounts it (Longhorn dynamic,
                                      # PV pvc-b32f29a6-e7d3-49d7-879a-5c3808c6dadf, RWO)
  shared: []                          # no gateway/envoy change (HTTPRoute untouched), no shared DB
                                      # (own SQLite + LanceDB on its own PVC), Ollama host is only
                                      # called, not changed. Longhorn: no volume op, just a re-attach.
depends_on: []
conflicts_with: [flux-oci-chart-sources, helm-drift-detection, flux-fleet-0.60.0, flux-reconciler-impersonation]
                                      # flux-oci-chart-sources: re-points the mintplex-labs HelmRepository
                                      #   that serves THIS HelmRelease's chart; a same-night source move
                                      #   makes a failed upgrade here ambiguous and muddies the revert.
                                      # helm-drift-detection: adds spec.driftDetection to every HR incl.
                                      #   ai/anythingllm and gates on "no Helm upgrade happened" — this
                                      #   plan IS a Helm upgrade of that HR, so its gate would read red.
                                      # flux-fleet-0.60.0: rolls helm-controller; an upgrade in flight
                                      #   across a controller restart is the ambiguity to avoid.
                                      # flux-reconciler-impersonation: exclusive anyway; listed so the
                                      #   pairing is explicit (ai namespace gets a new reconciler SA).
                                      # No open kube-prometheus-stack plan exists (91.4.1 executed
                                      #   2026-09-26); add any new one here, §4.4 reads Prometheus.
exclusive: false
security_ref: null                    # no security driver for this plan (see report / finding record)
capability_change: true               # TRUTHFUL, not defensive: 1.17.0 adds new agent web-search and
                                      # image-generation providers and reasoning-effort controls, and
                                      # changes user-visible behaviour (workspace settings now autosave
                                      # on edit; workspace temperature now applies to agents). None is
                                      # configured here, but the software can do things it could not.
rollback_class: git-revert            # no forward-only step: zero prisma migrations ship in this range
                                      # (§1), and §4.2 FAILS if the migration count moves. A local
                                      # tarball (§3.2) covers the residual case (§5.2).
finding_refs: []                      # `policy-cli.py finding list --grep anythingllm` (2026-10-02):
                                      # no version/plan-lane finding exists for 1.17; the two security
                                      # rows are AR-accepted register entries, not this plan's driver.
review: null
status: draft
window: null
premises:
  # All five run green 2026-10-02 while writing (plan-premises.py anythingllm-1.17).
  - id: live-image-still-1.16.2
    why: >-
      `current:` and the rollback target claim 1.16.2. If the Deployment already
      moved (a Step-0 direct-bump, or someone applied the floating tag), the
      baseline census and the revert target are wrong.
    run: kubectl get deploy -n ai anythingllm -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: mintplexlabs/anythingllm:1.16.2
  - id: manifest-pin-still-1.16.2
    why: "§3.3's sed anchors on the exact string `tag: \"1.16.2\"`; a changed pin makes it a silent no-op."
    run: grep -c 'tag. "1.16.2"' /Users/mu/code/cberg-home-nextgen/kubernetes/apps/ai/anythingllm/app/helmrelease.yaml
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
generated: "2026-10-02"
---

# anythingllm: 1.16.2 -> 1.17.0 (fixed pin for the floating `1.17`)

## 1. Summary & why held

AnythingLLM (namespace `ai`, Mintplex chart `anythingllm` 1.0.0, image
`mintplexlabs/anythingllm`) is the internal, multi-user-mode RAG workspace. State
lives on one RWO Longhorn PVC `anythingllm-storage-claim` (chart-created, dynamic
PV `pvc-b32f29a6-...`) mounted at `/app/server/storage`: a Prisma/SQLite DB
`anythingllm.db` (~0.9 MB) and a LanceDB store (`lancedb/paperless.lance`,
1241 vectors, 768-dim). LLM and embeddings go to the shared Ollama host; that
host is not touched.

**Why held.** Coverage saw target `1.17`, which has fewer version components
than the `1.16.2` pin: a floating series pointer, not a fixed version. The hold
is **correct in mechanism but resolvable today**. Measured 2026-10-02 against
Docker Hub (registry-1 manifest HEAD, OCI index digest) and GitHub:

| Probe | Result |
|---|---|
| `mintplexlabs/anythingllm:1.17` | 200, `sha256:f26f30df46916b6e...` |
| `mintplexlabs/anythingllm:1.17.0` | 200, **same** `sha256:f26f30df46916b6e...` |
| `:latest` | 200, same `sha256:f26f30df...` |
| `:1.17.1`, `:1.17.2`, `:1.17.3` | 404 |
| `:1.16.2` / `:1.16` | 200, both `sha256:480b0f105efd...` (== running pod imageID) |
| GitHub `Mintplex-Labs/anything-llm` `v1.17.0` | published 2026-10-01T22:17Z, `isPrerelease=false`, marked **Latest** |

So unlike the valkey `9.2` case (`penpot-cache-9.2`), `1.17` resolves to a GA
release, and this plan pins the **fixed** tag `1.17.0`. The floating `1.17` is
never written to the manifest. Other `pg-*`, `render-*`, `railway-*` tags are
other deployment variants and are not candidates.

**Release notes (v1.17.0, full changelog v1.16.2...v1.17.0, 63 commits).** No
"breaking" or "migration" section. The changes are about 55 bug fixes plus
features: Firecrawl agent web-search provider, Gemini and llmman image-generation
providers, reasoning-effort controls, a TogetherAI max_tokens setting, and
behaviour changes such as *"Autosave workspace settings on edit"* (#6343),
*"Apply workspace temperature to agents and omit the parameter when unset"*
(#6285), and *"send the Keep Alive setting on agent requests to Ollama"* (#6538).
The last one touches our Ollama path, but only on agent requests. That is why
`capability_change: true`.

**Data store / rollback evidence.** This is the deciding fact for
`rollback_class`. I checked it in the code, not the prose:

```bash
gh api repos/Mintplex-Labs/anything-llm/compare/v1.16.2...v1.17.0 -q '.files|length'            # 275 (< 300 API cap -> complete list)
gh api repos/Mintplex-Labs/anything-llm/compare/v1.16.2...v1.17.0 -q '.files[].filename' | grep -ci prisma   # 0
```

- **0 files under `server/prisma/`** (no `schema.prisma` change, no new
  `migrations/*`). On boot the image runs `prisma migrate deploy`, so with no
  new migration the DB is byte-compatible with 1.16.2. Live baseline:
  `_prisma_migrations` holds 40 finished rows.
- **`server/package.json` / `collector/package.json` change only `version`.**
  No dependency bump, so `@lancedb/lancedb` and `@prisma/client` are the same
  versions and the on-disk LanceDB format cannot change.
- `docker/Dockerfile` changes only `DEPLOYMENT_VERSION=1.17.0`. `.env.example`
  adds commented-out keys only.

Therefore a `git revert` returning to 1.16.2 is a complete rollback. §4.2
re-proves this after the fact: if the migration count moved, the gate fails and
§5.2 (tarball restore) applies.

## 2. Pre-checks

Run from `/Users/mu/code/cberg-home-nextgen` in zsh. Execute after the 03:00
`storage/daily-backup-all-volumes` job has finished.

```bash
cd /Users/mu/code/cberg-home-nextgen

# 2.0 Premises (the scheduler's gate; all five must PASS)
.venv/bin/python3 runbooks/plan-premises.py anythingllm-1.17

# 2.1 Target is still a GA fixed tag, and the floating 1.17 has not moved past it.
#     PASS: 1.17.0 -> 200 sha256:f26f30df46916b6e953e3a47ca98f48817726e3df635e62d4bfdd133292ecfff
#     and 1.17 shows the SAME digest. FAIL modes: 1.17.0 404 (pulled), or 1.17 now differs
#     (a 1.17.N shipped). In that case STOP and refresh this plan in place to the newest GA
#     1.17.N, re-running the §1 prisma/package compare for v1.16.2...v1.17.N.
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:mintplexlabs/anythingllm:pull" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
for t in 1.17.0 1.17 1.17.1; do
  printf '%-8s ' "$t"
  curl -s -I -H "Authorization: Bearer $TOKEN" \
    -H "Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json" \
    "https://registry-1.docker.io/v2/mintplexlabs/anythingllm/manifests/$t" \
    | grep -i -E '^HTTP|docker-content-digest' | tr -d '\r' | tr '\n' ' '; echo
done
gh release view v1.17.0 -R Mintplex-Labs/anything-llm --json isPrerelease -q .isPrerelease   # PASS: false

# 2.2 Last night's backup of the data volume COMPLETED (the last-resort restore source, §5.3).
#     PASS: prints BACKUP_FRESH. Prints BACKUP_STALE if the newest Completed backup is > 26h old,
#     NO_BACKUP if none exist (both STOP).
kubectl get backups.longhorn.io -n storage -l backup-volume=pvc-b32f29a6-e7d3-49d7-879a-5c3808c6dadf -o json \
  | python3 -c "
import sys,json,datetime as d
b=[x for x in json.load(sys.stdin)['items'] if x.get('status',{}).get('state')=='Completed']
if not b: print('NO_BACKUP'); sys.exit(1)
t=max(x['status']['backupCreatedAt'] for x in b)
age=(d.datetime.now(d.timezone.utc)-d.datetime.fromisoformat(t.replace('Z','+00:00'))).total_seconds()/3600
print(('BACKUP_FRESH' if age<26 else 'BACKUP_STALE'), t, f'{age:.1f}h')"

# 2.3 Pod healthy, zero restarts, nothing in flight
kubectl get pods -n ai -l app.kubernetes.io/name=anythingllm \
  -o 'custom-columns=NAME:.metadata.name,PHASE:.status.phase,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount'
flux get kustomizations -n ai anythingllm
flux get helmreleases -n ai anythingllm
```

**2.4 Baseline CONTENTS census.** This script is read-only: Prisma `count()`,
a LanceDB count plus vector search, and one unauthenticated GET. It was
dry-run live on 2026-10-02 and produced `workspaces=2 workspace_documents=293
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
# api_multiuser=true. Any other prisma_migrations value means the baseline moved -> re-read §1.
grep -c -i -E '^(CENSUS_ERROR|lance_[a-z]+=0$)' /tmp/allm-pre.txt   # PASS: 0
```

## 3. Steps

**3.1 Silence + update marker** (docs/sops/application-update.md Step 1). Scope
the silence to AnythingLLM's own alerts and pods. Do NOT silence the whole
namespace `ai`: other plans (e.g. `app-template-5.2.1`) roll workloads in `ai`
and their alerts must still fire.

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
    "comment":"anythingllm 1.16.2->1.17.0 (plan anythingllm-1.17). auto-expires 2h"}'; echo
done
kill $PF 2>/dev/null
runbooks/update-marker.sh add anythingllm ai 2 "1.16.2->1.17.0 (plan anythingllm-1.17)"
```

**3.2 Off-cluster snapshot of the data** (the §5.2 restore source). This is a
read-only `tar` streamed to the Mac, with no write to the PVC. Dry-run
2026-10-02: 5.0 MB, 885 entries.

```bash
P=$(kubectl -n ai get pod -l app.kubernetes.io/name=anythingllm -o jsonpath='{.items[0].metadata.name}')
SNAP=$HOME/anythingllm-pre-1.17.0-$(date +%Y%m%d_%H%M%S).tgz
kubectl -n ai exec "$P" -c anythingllm -- tar czf - -C /app/server/storage anythingllm.db lancedb > "$SNAP"
ls -l "$SNAP"; tar tzf "$SNAP" | grep -c -E '^(anythingllm\.db|lancedb/)'   # PASS: size > 1 MB AND count > 100
echo "$SNAP" > /tmp/allm-snap-path.txt
```

**3.3 Bump the pin** (dry-tested on a scratch copy with BSD sed; the resulting
diff is below):

```bash
sed -i '' 's/tag: "1\.16\.2"/tag: "1.17.0"/' kubernetes/apps/ai/anythingllm/app/helmrelease.yaml
git diff kubernetes/apps/ai/anythingllm/app/helmrelease.yaml
# expected, exactly one hunk:
# -      tag: "1.16.2"
# +      tag: "1.17.0"
```

**3.4 Commit + push** (shared worktree rules: `--only`, then verify):

```bash
printf '%s\n\n%s\n' "chore(anythingllm): 1.16.2 -> 1.17.0 (fixed pin for floating 1.17; plan anythingllm-1.17)" \
  "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>" > /tmp/allm-msg.txt
git commit --only kubernetes/apps/ai/anythingllm/app/helmrelease.yaml -F /tmp/allm-msg.txt
git log -1 --format=%s     # must be the subject above; amend before push if not
git show --stat HEAD       # exactly 1 file: kubernetes/apps/ai/anythingllm/app/helmrelease.yaml
git push
```

**3.5 Watch the rollout.** Flux picks it up by webhook; no manual reconcile is
needed. Recreate stops the old pod, then the init container `clear-vector-cache`
runs (it wipes only `vector-cache/` and `comkey`, which is expected on every
start), and then the new pod starts. Readiness needs 2 successes 10 s apart on
`:8888/v1/api/health`.

```bash
flux get helmreleases -n ai anythingllm      # wait until REVISION advances and READY True (<= 10 min)
kubectl get pods -n ai -l app.kubernetes.io/name=anythingllm \
  -o 'custom-columns=NAME:.metadata.name,PHASE:.status.phase,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount,IMAGE:.status.containerStatuses[0].imageID'
```

## 4. Verification

Wait at least 5 minutes after the new pod is Ready before running 4.4. The
AnythingLLM alert rules use `for: 5m` / `for: 1m` over 15-minute windows.

**4.1 The running artifact is the pinned GA digest, not just the tag.**
`rollout status` can green-light the old generation, and a Helm remediation
rollback would leave git at 1.17.0 while the pod runs 1.16.2.

```bash
P=$(kubectl -n ai get pod -l app.kubernetes.io/name=anythingllm -o jsonpath='{.items[0].metadata.name}')
kubectl -n ai get pod "$P" -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'
kubectl -n ai exec "$P" -c anythingllm -- printenv DEPLOYMENT_VERSION
```
PASS: imageID ends with
`sha256:f26f30df46916b6e953e3a47ca98f48817726e3df635e62d4bfdd133292ecfff`
(Docker Hub index digest; containerd reports the index digest for a
multi-arch pull, which is what the 1.16.2 pod shows today:
`...@sha256:480b0f10...` == Hub `1.16.2`), AND `DEPLOYMENT_VERSION` prints
`1.17.0`. FAIL looks like: `480b0f10...` / `1.16.2` (rollback or old pod), or
any other digest (the tag was re-pushed between §2.1 and the pull, so treat it
as a non-reviewed artifact and roll back).

**4.2 CONTENTS ASSERTION: the DB and the vector store are the same data, readable by 1.17.0, and no migration ran.**
This is measured by the §2.4 census inside the NEW pod and compared to `/tmp/allm-pre.txt`.

```bash
P=$(kubectl -n ai get pod -l app.kubernetes.io/name=anythingllm -o jsonpath='{.items[0].metadata.name}')
kubectl -n ai exec -i "$P" -c anythingllm -- sh -c 'cd /app/server && node -' < /tmp/allm-census.js \
  | grep -v '^prisma:' > /tmp/allm-post.txt
python3 /tmp/allm-compare.py /tmp/allm-pre.txt /tmp/allm-post.txt
```
PASS: `CENSUS_OK (11 keys identical)`, exit 0. `workspace_chats` may only grow.
Each key guards against a specific failure:
- `prisma_migrations` changed (for example `40->41`): a forward-only migration
  ran, so the git-revert rollback is no longer sufficient. Go to §5.2 if
  rolling back.
- `MISSING lance_paperless`: LanceDB is unreadable or empty.
- `api_multiuser` changed to `false`, or `api_vectordb` changed: the server
  booted against a fresh or empty settings table. The census prints that state
  and does not error, which is why the keys are compared.
- A `CENSUS_ERROR` line: Prisma or LanceDB cannot open the store.

Negative control, run 2026-10-02 against a tampered post file
(`prisma_migrations=41`, lance keys removed): it printed `CENSUS_FAIL` with
three reasons and exited 1. An empty pre file also fails (`PRE census
empty/errored`), so a baseline that was never captured cannot pass.

**4.3 Serving path through the Gateway** (the user-facing route, not just the
pod):

```bash
H=$(kubectl get httproute -n ai anythingllm -o jsonpath='{.spec.hostnames[0]}')
curl -s -o /dev/null -w '%{http_code}\n' "https://$H/api/ping"                 # PASS: 200
curl -s "https://$H/api/ping"                                                    # PASS: {"online":true}
```
FAIL looks like: 503 or `no healthy upstream` from Envoy (no ready
endpoints), or a body that is not `{"online":true}`.

**4.4 Alert state after the soak, read from Prometheus.**

```bash
kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=ALERTS%7Balertname%3D~%22AnythingLLM.%2A%22%2Calertstate%3D%22firing%22%7D' \
  | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print('FIRING', [x['metric']['alertname'] for x in r]) if r else print('NONE_FIRING')"
kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=kube_deployment_status_replicas_available%7Bnamespace%3D%22ai%22%2Cdeployment%3D%22anythingllm%22%7D' \
  | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print('AVAIL', r[0]['value'][1] if r else 'ABSENT')"
```
PASS: `NONE_FIRING` AND `AVAIL 1`. `AVAIL ABSENT` is a FAIL: it means
kube-state-metrics or Prometheus is not answering, not that everything is fine.
The alert query is evaluated in Prometheus, so it still reports alerts that the
§3.1 silence hides from Alertmanager.

CONTROL: metric kube_deployment_status_replicas_available — `{namespace="ai",deployment="anythingllm"}` must be 1 (measured present 2026-10-02, value 1); absent = FAIL.
CONTROL: metric kube_pod_container_status_restarts_total — `{namespace="ai",container="anythingllm"}` for the NEW pod must be 0 at T+5m (series measured present 2026-10-02).
CONTROL: alertname AnythingLLMPodCrashLooping — must NOT be firing at T+5m (rule in `kubernetes/apps/monitoring/kube-prometheus-stack/app/anythingllm-alerts.yaml`).
CONTROL: alertname AnythingLLMPodNotReady — must NOT be firing at T+5m (same rule file).

**4.5 Clean up** after all gates pass. Delete the two silences (IDs were
printed in §3.1), or let them expire after 2 h. Then run
`runbooks/update-marker.sh clear anythingllm`. Keep
the §3.2 tarball for 7 days, then delete it.

## 5. Rollback

**5.1 Standard path: git revert (sufficient whenever §4.2 shows `prisma_migrations=40`).**

```bash
cd /Users/mu/code/cberg-home-nextgen
SHA=$(git log -1 --format=%H -- kubernetes/apps/ai/anythingllm/app/helmrelease.yaml)
git show --stat "$SHA"      # confirm it is the 3.4 bump commit
git revert --no-edit "$SHA"
git log -1 --format=%s      # must read: Revert "chore(anythingllm): 1.16.2 -> 1.17.0 ..."
git push
```
Confirm that the cluster is back. Run the same two commands as §4.1: the
imageID must end in `sha256:480b0f105efd6a4c8a4cde82713fe81348d75c979a24a38e9ed8e236bed0fd17`
and `DEPLOYMENT_VERSION` must print `1.16.2`. Then re-run the §4.2 census and
compare it against `/tmp/allm-pre.txt`; it must print `CENSUS_OK`.

If the HelmRelease is stuck (Ready=False with `upgrade retries exhausted`),
`maxHistory: 1` means `helm rollback` cannot reach the old revision. Pushing
the revert is still the fix. If the HR does not re-attempt on its own, run
`flux reconcile helmrelease -n ai anythingllm --force` once (SOP
application-update §6).

**5.2 Data restore from the §3.2 tarball.** Use this only if §4.2 showed a
moved `prisma_migrations` or a missing or changed key AND 1.16.2 fails against
the current data after 5.1.

```bash
SNAP=$(cat /tmp/allm-snap-path.txt); ls -l "$SNAP"
P=$(kubectl -n ai get pod -l app.kubernetes.io/name=anythingllm -o jsonpath='{.items[0].metadata.name}')
# image must already be 1.16.2 (5.1 done). Move the current state aside on the PVC, then unpack:
kubectl -n ai exec "$P" -c anythingllm -- sh -c 'cd /app/server/storage && mv anythingllm.db anythingllm.db.failed-1.17.0 && mv lancedb lancedb.failed-1.17.0'
kubectl -n ai exec -i "$P" -c anythingllm -- tar xzf - -C /app/server/storage < "$SNAP"
kubectl -n ai delete pod "$P"     # Recreate -> fresh 1.16.2 process opens the restored files
```
Confirm with the §4.2 census against `/tmp/allm-pre.txt` (must print
`CENSUS_OK`). The `*.failed-1.17.0` copies stay on the PVC for forensics. Delete
them only after the operator confirms.

**5.3 Last resort: Longhorn backup.** Use this only if the tarball is unusable.
Restore the newest Completed backup that §2.2 confirmed (volume
`pvc-b32f29a6-e7d3-49d7-879a-5c3808c6dadf`) by following
`docs/sops/backup.md` (restore to a new volume name, then rebind PV/PVC). That
path is operator-attended, because this PVC is chart-created with a UUID PV and
the rebind means editing the claim.

## 6. Interference notes

- **Outage:** about 1–2 min of the AnythingLLM UI/API (Recreate). No other app
  calls AnythingLLM in-cluster. The only repo references outside its folder are
  the `ai` kustomization and its own alert rules.
- **Shared infra:** none perturbed. The HTTPRoute on `envoy-internal` is
  unchanged. The Ollama host (192.168.30.111) receives only its normal startup
  calls, plus (new in 1.17.0) a keep-alive field on agent requests. No pinned
  model is touched.
- **Same-namespace plans:** `app-template-5.2.1` and `redis-fleet-8.10.2` both
  touch other workloads in `ai`. They do not collide on any resource. The
  §3.1 silence is scoped to `pod=~anythingllm-.*` so it cannot hide their
  alerts.
- **Ordering:** run after the 03:00 Longhorn backup has completed (§2.2 gates
  this). No dependency on any other plan.
- **conflicts_with rationale:** see frontmatter. In short: anything that moves
  this HelmRelease's chart source, adds a spec field to every HR while asserting
  "no Helm upgrade", or restarts helm-controller must not share the slot.
- **If upstream ships 1.17.N before the window:** §2.1 fails by design (the
  floating `1.17` digest no longer matches `1.17.0`). Refresh this plan in
  place (keep `plan_id`). Re-run the §1 compare against v1.17.N, specifically
  the prisma file count and the package.json dependency diff. Update the
  digests in §2.1/§4.1, then re-review.
- **Repo corrections noticed (not acted on here):**
  `kubernetes/apps/ai/anythingllm/app/pvc.yaml` declares
  `pvc/anythingllm-storage` but is **not listed** in the app's
  `kustomization.yaml`, and no such PVC exists live. The real claim is the
  chart-created `anythingllm-storage-claim`. The orphan file misleads any
  storage audit that greps the repo. Its PV is a UUID `longhorn` dynamic
  volume, which is out of line with the speaking-name rule in
  `docs/sops/longhorn.md`. That would be its own migration plan, not part of
  this bump.
