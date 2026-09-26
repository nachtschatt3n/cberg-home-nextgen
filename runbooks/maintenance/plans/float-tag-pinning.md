---
plan_id: float-tag-pinning
component: makemkv                    # the component of the CURRENT batch (Batch M). This file is a
                                      # PROGRAMME (see §2); `component`/`current`/`target`/`touches`
                                      # describe the ONE batch that is executable now, and rotate to
                                      # the next batch when it is re-planned.
pr: null                              # No Renovate PR is possible for a floating tag — that IS the
                                      # defect. After this pin Renovate sees `v26.01.1` and CAN
                                      # propose newer tags (drift becomes visible).
kind: config
current: "jlesage/makemkv:latest (running index digest sha256:12ce7fc0e398... == v26.01.1)"
target: "jlesage/makemkv:v26.01.1@sha256:12ce7fc0e398c240bc06b27459241ddae524e066c476525b9b36a16c3e478518"
update_type: hardening                # drift visibility; no version moves (byte-neutral by construction)
risk: low                             # Batch M only: one single-replica Deployment, already
                                      # strategy Recreate, idle, pinned to the EXACT digest it runs.
est_duration_min: 20                  # Batch M: edit+push+reconcile ~5, Recreate + gates ~10, slack 5
needs_reboot: false
touches:
  namespaces: [media]
  resources:
    - helmrelease/makemkv
    - deployment/makemkv
    - pvc/makemkv-config              # RWO Longhorn, remounted by the new pod; not modified
    - pvc/makemkv-media               # CIFS (cifs-makemkv-media), remounted; not modified, not deleted
    - "docker.io/jlesage/makemkv@sha256:12ce7fc0e398c240bc06b27459241ddae524e066c476525b9b36a16c3e478518"
  shared: []                          # consumer only: the new pod re-claims ONE gpu.intel.com/i915
                                      # slot (5 allocatable per node; 4 used on nuc14-03, 2 on -01,
                                      # 1 on -02, measured 2026-09-26). It perturbs no shared infra;
                                      # the i915 interaction is expressed via conflicts_with below.
depends_on: []
conflicts_with:
  - nocodb-2026.09.0                  # declared on nocodb's side (its old reason: Batch B named
                                      # nocodb). That file-level collision is GONE — nocodb runs a
                                      # calver tag (2026.08.2) and is not in any remaining batch —
                                      # but the declaration stands until nocodb's file drops it, so
                                      # it is named here too. In an on-demand run it only forces
                                      # serial order + settle_before (run-now.py conflict_pairs).
  # - intel-device-plugin-0.37.0   # RESOLVED 2026-09-26: executed + retired in the now:2026-09-26 run; ref removed
exclusive: false
security_ref: null                    # CORRECTED 2026-09-26: was F-c58dd98e, which is an unrelated
                                      # (absenty, resolved) finding. No security finding exists for
                                      # makemkv — the sweep raises float warnings only for images
                                      # with fixable CVEs.
finding_refs: [F-aa4d1184, F-eed33ead]  # the two OPEN floating-tag findings in this plan's
                                      # namespaces (oc8 pg15 init container, oc8 caddy) — Batch O,
                                      # NOT closed by Batch M. Kept here so the programme owns them.
capability_change: false
rollback_class: git-revert            # Batch M changes addressability only, not bytes.
autonomy_override: human-gated        # A PROGRAMME: which batch runs when is an operator call.
status: draft    # Batch M EXECUTED 2026-09-26 (ab5a41b3). Programme stays open: Batch O not yet planned; component/current/target/touches/premises below still describe Batch M and must be rotated when Batch O is planned
window: null     # reset after Batch M ran in now:2026-09-26
generated: "2026-09-26"               # Batch M re-planned 2026-09-26 by plan-reviewer from a LIVE
                                      # inventory; the 2026-09-06 inventory (19 images) is obsolete.
sops_refs:
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/storage-safety.md
premises:
  - id: makemkv-deploy-still-on-latest
    why: "Batch M pins `latest`. If the Deployment already moved, the pin target below is stale."
    run: kubectl get deploy -n media makemkv -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: jlesage/makemkv:latest
  - id: makemkv-running-digest-is-v26.01.1
    why: "The pin is byte-neutral ONLY if the running pod's imageID is exactly this digest. Exactly one pod, or the output has two entries and fails."
    run: kubectl get pod -n media -l app.kubernetes.io/name=makemkv -o jsonpath='{.items[*].status.containerStatuses[0].imageID}'
    expect_exact: docker.io/jlesage/makemkv@sha256:12ce7fc0e398c240bc06b27459241ddae524e066c476525b9b36a16c3e478518
  - id: makemkv-strategy-recreate
    why: "RWO Longhorn config PVC + replicas 1: RollingUpdate would Multi-Attach deadlock on a cross-node surge."
    run: kubectl get deploy -n media makemkv -o jsonpath='{.spec.strategy.type}'
    expect_exact: Recreate
  - id: makemkv-hr-ready
    why: "A HelmRelease that is already failing would make the post-push Ready gate unattributable."
    run: kubectl get helmrelease -n media makemkv -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: repo-has-exactly-two-latest-sites
    why: "The §3 edit script asserts exactly one match per site; this is the same fact read from git HEAD."
    run: 'git show HEAD:kubernetes/apps/media/makemkv/app/helmrelease.yaml | grep -c "tag: latest"'
    expect_exact: "2"
---

# Pin floating image tags — programme, with Batch M (makemkv) executable now

## 1. Why this is a security-class item, not tidiness

A floating tag means the running bytes can change with no manifest edit, no Flux
event, no Renovate PR and no diff. Renovate's `helm-values` manager needs a
version-shaped tag to diff, so a floating tag never produces a PR.

**Measured on makemkv, 2026-09-26 — the float is live, not theoretical.** The
pod on k8s-nuc14-03 runs index digest `sha256:12ce7fc0…`, which Docker Hub maps to
`v26.01.1` (published 2026-01-05). Docker Hub's `latest` today is
`sha256:bfdddd29…` (`v26.09.2`). The pod was recreated on 2026-09-06 and still got
the January bytes because `pullPolicy: IfNotPresent` reused the node's cached
`latest`. A reschedule onto nuc14-01/02 would silently jump eight months of
releases. Pinning to the running digest freezes today's bytes and makes the gap
visible to Renovate.

## 2. Programme state — LIVE inventory 2026-09-26 (replaces the 2026-09-06 list)

Scan: every Deployment/StatefulSet/DaemonSet/CronJob in the cluster, every
container + initContainer, classified with the sweep's own definition
(`_is_mutable_tag_ref` in `runbooks/security-check.py`: no `@sha256:` AND tag in
{latest, stable, dev, edge, main, master, nightly, rolling} or a bare-major
line tag). Result — 10 refs, 4 images:

| Batch | Namespace / workload | Image | Open finding | Status |
|---|---|---|---|---|
| M (done) | media/makemkv | `jlesage/makemkv:latest` -> `v26.01.1@sha256:12ce7fc0…` | none (no fixable-CVE warning) | **DONE 2026-09-26 in now:2026-09-26, pin commit ab5a41b3; G1/G2/G3 green, imageID unchanged** |
| O (later) | ai/oc8-caddy | `caddy:2` | F-eed33ead | later window |
| O (later) | ai/oc8-redis | `redis:7-alpine` | none | later window |
| O (later) | ai/oc8-{backend,worker,scheduler,ingestion-worker} init `wait-for-postgres` | `pgvector/pgvector:pg15` | F-aa4d1184 | later; the image is hard-coded in the FORK chart `deploy/helm/oc8` (GitRepository source), so the fix is a fork commit, not an edit in this repo |
| — | office/nextcloud, nextcloud-mariadb | `bitnamilegacy/mariadb:latest` | F-ac22c0ba (AR-010) | owned by `bitnamilegacy-exit-nextcloud-db`; do not touch here |
| — | default/echo-server | `http-https-echo:41` | none | outside this plan's namespaces; add to Batch O or drop |

**Done since the 2026-09-06 draft (verified live, no action):** paperless-ai,
paperless-gpt, trmnl-ha, hermes-agent, paperclip, actual-server, nocodb, scrypted,
phpmyadmin, busybox:latest/stable, node:22-bookworm, pgvector:pg16, the
media/library-tools and ai/openclaw python sites (all now `python:3.14.7-slim`),
librechat's bitnami/mongodb (digest-pinned). Their floating-tag findings are
resolved in sweep_findings.

**Owned by other plans today (excluded):** download/tube-archivist sync jobs
(`tube-archivist-sync-python-3.14.7`), the crash-ghost-reaper and
elasticsearch-obs-recovery python images (their own plans), paperclip, nocodb,
nextcloud, paperless, mqttx, unpoller.

**Batch O preconditions (not today):** `oc8-install` is `status: blocked` and
describes this workload; resolve ownership with that plan first. oc8's
HelmRelease takes values from a Secret (`oc8-values`) plus inline values, and the
chart comes from a GitRepository with `reconcileStrategy: Revision` — any pin
re-renders the whole release, so Batch O needs its own helm-template diff and
premises. `redis:7-alpine` restart drops in-memory queue state.

## 3. Batch M — steps (attended; no reboot; serial)

State lives in files (Bash calls share no variables):

```bash
ST=/private/tmp/claude-501/float-tag-pinning-20260926
mkdir -p "$ST"
```

### 3.0 Premises + pre-checks (read-only; any failure = STOP)

```bash
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 runbooks/plan-premises.py float-tag-pinning --require-premises || { echo STOP-premises; exit 1; }
```

```bash
# Upstream still maps v26.01.1 to the running digest, and the index is pullable by digest
# (a reschedule to a node without the cache must be able to fetch it).
curl -fsS https://hub.docker.com/v2/repositories/jlesage/makemkv/tags/v26.01.1 \
  | python3 -c "import sys,json; d=json.load(sys.stdin)['digest']; print(d); sys.exit(0 if d=='sha256:12ce7fc0e398c240bc06b27459241ddae524e066c476525b9b36a16c3e478518' else 1)" \
  || { echo STOP-tag-moved; exit 1; }
T=$(curl -fsS "https://auth.docker.io/token?service=registry.docker.io&scope=repository:jlesage/makemkv:pull" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
code=$(curl -s -o /dev/null -w '%{http_code}' -I -H "Authorization: Bearer $T" \
  -H 'Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json' \
  https://registry-1.docker.io/v2/jlesage/makemkv/manifests/sha256:12ce7fc0e398c240bc06b27459241ddae524e066c476525b9b36a16c3e478518)
echo "registry HEAD $code"; [ "$code" = 200 ] || { echo STOP-not-pullable; exit 1; }
```

```bash
# Record the OLD pod (the gates must read a DIFFERENT pod) and its imageID.
kubectl get pod -n media -l app.kubernetes.io/name=makemkv -o jsonpath='{.items[0].metadata.name}' > /private/tmp/claude-501/float-tag-pinning-20260926/old_pod
kubectl get pod -n media -l app.kubernetes.io/name=makemkv -o jsonpath='{.items[0].status.containerStatuses[0].imageID}' > /private/tmp/claude-501/float-tag-pinning-20260926/old_imageid
cat /private/tmp/claude-501/float-tag-pinning-20260926/old_pod; echo; cat /private/tmp/claude-501/float-tag-pinning-20260926/old_imageid; echo
```

```bash
# Not mid-rip: a rip spawns `makemkvcon ... mkv ...`; idle shows only `makemkvcon guiserver`.
# Operator (attended) also confirms no disc is in the drive.
kubectl exec -n media deploy/makemkv -- ps -o args | grep makemkvcon
n=$(kubectl exec -n media deploy/makemkv -- ps -o args | grep -c "makemkvcon.* mkv "); echo "rip processes: $n"
[ "$n" = 0 ] || { echo STOP-rip-in-progress; exit 1; }
```

### 3.1 Edit (python, exact-once assertions; dry-tested 2026-09-26 on a scratch copy — second run fails loudly, `helm template` diff is exactly one line)

Both `tag: latest` sites are edited. Only the `controllers.main.containers.main.image`
site renders; the top-level `image:` block is INERT under app-template 5.1.0
(measured: changing it alone leaves `helm template` output byte-identical). It is
pinned anyway so no `latest` string remains to mislead a grep.

```bash
cd /Users/mu/code/cberg-home-nextgen
python3 - kubernetes/apps/media/makemkv/app/helmrelease.yaml <<'EOF'
import sys
path = sys.argv[1]
PIN = "v26.01.1@sha256:12ce7fc0e398c240bc06b27459241ddae524e066c476525b9b36a16c3e478518"
EDITS = (
    ("    image:\n      repository: jlesage/makemkv\n      tag: latest\n",
     "    image:\n      repository: jlesage/makemkv\n      tag: " + PIN + "\n"),
    ("            image:\n              repository: jlesage/makemkv\n              tag: latest\n",
     "            image:\n              repository: jlesage/makemkv\n              tag: " + PIN + "\n"),
)
s = open(path).read()
for old, new in EDITS:
    n = s.count(old)
    assert n == 1, f"expected exactly 1 match, got {n}: {old!r}"
    s = s.replace(old, new)
assert "tag: latest" not in s, "a 'tag: latest' survived"
open(path, "w").write(s)
print("OK pinned 2 sites")
EOF
git diff --stat -- kubernetes/apps/media/makemkv/app/helmrelease.yaml   # expect: 1 file, 2 insertions, 2 deletions
```

### 3.2 Commit + push (shared worktree)

```bash
cd /Users/mu/code/cberg-home-nextgen
MSG=/private/tmp/claude-501/float-tag-pinning-20260926/msg-float-tag-pinning-$(date +%s).txt
printf '%s\n' "fix(makemkv): pin jlesage/makemkv latest -> v26.01.1@sha256 (running digest)" "" \
  "Float-tag-pinning Batch M. Byte-neutral: pins the index digest the pod already runs." \
  > "$MSG"; echo "$MSG" > /private/tmp/claude-501/float-tag-pinning-20260926/msgfile
```

```bash
cd /Users/mu/code/cberg-home-nextgen
git commit --only kubernetes/apps/media/makemkv/app/helmrelease.yaml -F "$(cat /private/tmp/claude-501/float-tag-pinning-20260926/msgfile)"
git show --stat HEAD     # exactly ONE file: kubernetes/apps/media/makemkv/app/helmrelease.yaml
git log -1 --format=%s   # must be the makemkv subject above
git rev-parse HEAD > /private/tmp/claude-501/float-tag-pinning-20260926/pin_sha
git push origin main
```

### 3.3 Reconcile

```bash
flux reconcile kustomization makemkv -n media --with-source
flux reconcile helmrelease makemkv -n media
kubectl rollout status deploy/makemkv -n media --timeout=5m
```

## 4. Verification (all gates read the NEW pod; each can FAIL)

**G1 — byte-neutrality (the proof).** New pod name differs from `old_pod`, exactly
one pod, spec image is the pin, imageID equals `old_imageid`.

```bash
ST=/private/tmp/claude-501/float-tag-pinning-20260926
kubectl get pod -n media -l app.kubernetes.io/name=makemkv -o json | python3 -c "
import sys,json
st='$ST'
old_pod=open(st+'/old_pod').read().strip(); old_id=open(st+'/old_imageid').read().strip()
items=[p for p in json.load(sys.stdin)['items'] if not p['metadata'].get('deletionTimestamp')]
assert len(items)==1, f'FAIL: {len(items)} pods'
p=items[0]; name=p['metadata']['name']; cs=p['status']['containerStatuses'][0]
spec=p['spec']['containers'][0]['image']
print('pod',name,'| spec',spec,'| imageID',cs['imageID'])
assert name!=old_pod, 'FAIL: still the OLD pod (rollout not happened)'
assert spec=='jlesage/makemkv:v26.01.1@sha256:12ce7fc0e398c240bc06b27459241ddae524e066c476525b9b36a16c3e478518', 'FAIL: pin not rendered (wrong values path?)'
assert cs['imageID']==old_id=='docker.io/jlesage/makemkv@sha256:12ce7fc0e398c240bc06b27459241ddae524e066c476525b9b36a16c3e478518', 'FAIL: bytes changed'
print('G1 PASS'); open(st+'/new_pod','w').write(name)
"
```

Can-fail evidence: (a) a pin at the inert top-level values path leaves the
rendered spec `jlesage/makemkv:latest` (measured with `helm template`, 2026-09-26)
→ the `spec` assertion fails; (b) a pod that pulled `latest` on a cold node
reads imageID `…@sha256:bfdddd29…` (Docker Hub `latest` today) → the imageID
assertion fails; (c) reading before the Recreate returns `old_pod` → fails.

**G2 — the app serves (positive match).** HTTP 200 from nginx inside the NEW pod.

```bash
NEW=$(cat /private/tmp/claude-501/float-tag-pinning-20260926/new_pod)
kubectl exec -n media "$NEW" -- sh -c 'wget -q -S -O /dev/null http://127.0.0.1:5800/ 2>&1 | head -1' | grep -q "200 OK" && echo "G2 PASS" || { echo "G2 FAIL"; exit 1; }
kubectl get endpoints -n media makemkv -o jsonpath='{.subsets[0].addresses[0].targetRef.name}'; echo "  (must equal $NEW)"
```

Can-fail evidence: the same probe against a closed port (5801) prints nothing and
`grep -q` fails (measured 2026-09-26); before nginx starts, the same happens.

**G3 — stable after 3 min.** `restartCount` 0 and Ready on the new pod; HR Ready.

```bash
NEW=$(cat /private/tmp/claude-501/float-tag-pinning-20260926/new_pod)
kubectl get pod -n media "$NEW" -o jsonpath='{.status.containerStatuses[0].restartCount}/{.status.containerStatuses[0].ready}{"\n"}'   # PASS: 0/true
kubectl get helmrelease -n media makemkv -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'                          # PASS: True
```

**Informational only (NOT a gate):** the sweep's floating-tag finding count does
not change for Batch M — makemkv never had a finding, so a count gate here would
pass on every outcome.

## 5. Close-out — do NOT retire this file

Batch M executing does not finish the programme. Do **not** set
`status: executed` and do **not** delete the file (the window agent's default on
success), or `finding_refs` F-aa4d1184 / F-eed33ead lose their owner. Instead, in
one commit (`git commit --only runbooks/maintenance/plans/float-tag-pinning.md`):
move the Batch M row in §2 to "done" with the pin commit sha, reset `window: null`,
keep `status: draft`, and rotate `component/current/target/touches/premises` to
Batch O when it is planned. Ack the home-operation issue with
`--by executed --note "<pin sha> (Batch M only; programme continues)"`.

## 6. Rollback

Trigger: G1/G2/G3 FAIL, or the new pod sits Pending/ImagePullBackOff > 5 min.

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit "$(cat /private/tmp/claude-501/float-tag-pinning-20260926/pin_sha)"
git show --stat HEAD; git log -1 --format=%s
git push origin main
flux reconcile kustomization makemkv -n media --with-source
flux reconcile helmrelease makemkv -n media
```

Caveat, measured: the revert restores `tag: latest`, which is byte-neutral ONLY if
the pod lands on k8s-nuc14-03 (the node holding the cached January `latest`). On
nuc14-01/02 `latest` pulls `v26.09.2` — a real version jump. After a revert, read
the new pod's imageID; if it is not `…12ce7fc0…`, tell the operator the app moved
versions. No data is at risk either way: the config PVC (RWO Longhorn) and the
CIFS media PVC are remounted, never modified or deleted; no forward-only step exists.

## 7. Later (NOT this batch)

- Raising makemkv to a newer release is a separate change. Once pinned, Renovate /
  `coverage.py` can propose `v26.09.2`; whether the nightly Step 0 lane auto-applies
  it depends on its classification of this calver jump — decide deliberately
  (deny rule or accept) rather than discovering it.
- Batch O per §2.
