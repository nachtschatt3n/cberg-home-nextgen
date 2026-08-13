---
plan_id: langfuse-3.225.1
component: langfuse
pr: null                              # no Renovate PR — images are literal tags in raw
                                      # manifests (not Renovate-tracked). Hold source is the
                                      # fresh Trivy scan (security-check-current.md, 2026-08-06).
kind: image
current: "langfuse 3.111.0 / clickhouse 24.1-alpine"
target: "langfuse 3.225.1 / clickhouse 25.3-alpine"
update_type: minor                    # langfuse stays in major 3 (3.111→3.225, ~114 minors);
                                      # clickhouse crosses one CH year-major (24→25) — see Summary
risk: medium
est_duration_min: 40
needs_reboot: false                   # app pods only, no Talos/node reboot
touches:
  namespaces: [ai]
  resources:
    - deployment/langfuse-web         # image langfuse/langfuse 3.111.0 -> 3.225.1 (+ minio sidecar unchanged)
    - deployment/langfuse-worker      # image langfuse/langfuse-worker 3.111.0 -> 3.225.1 (lockstep w/ web)
    - deployment/langfuse-clickhouse  # image clickhouse-server 24.1-alpine -> 25.3-alpine; Recreate strategy
    - pvc/langfuse-clickhouse-data-new # ClickHouse on-disk format upgraded in place (two CH majors)
    - pvc/langfuse-postgresql-data-new # langfuse Prisma migrations write here on web/worker startup
    - deployment/langfuse-postgresql  # not re-imaged (stays postgres:15) but receives schema migrations
    - ingress/langfuse                # class "external" — nginx backend endpoint swap only, no controller restart
  shared: []                          # langfuse runs its OWN dedicated postgres/redis/clickhouse/zookeeper/
                                      # minio inside the ai ns — NOT the cluster-shared postgres, NOT a shared
                                      # ClickHouse. ingress-controller not perturbed (backend swap only). No
                                      # cert-manager/cilium/coredns/longhorn-control-plane touched.
depends_on: []
conflicts_with: []                    # none pending. Co-tenant caution (openclaw + other ai-ns apps) is a
                                      # scheduling note, not shared data — see Interference.
status: awaiting-go                 # thu-early:2026-08-13 unattended run: medium risk ⇒ deferred, go/no-go routed via home-operation (issue langfuse-3.225.1)
window: "thu-early:2026-08-13"       # CVE remediation batch (no-reboot); window-agent sequences w/ the others
                                      # chosen over the 60-min weekday slots for migration headroom;
                                      # operator-present preferred (it mutates two data stores).
auto_execute: false                   # data-store migrations — never unattended
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/langfuse-clickhouse-maintenance.md
  - docs/sops/backup.md
  - docs/sops/storage-safety.md
generated: "2026-08-06"
---

# langfuse 3.111.0 → 3.225.1  +  clickhouse 24.1-alpine → 25.3-alpine

## 1) Summary & why held

CVE-remediation image bump of the **langfuse LLM-observability stack** in namespace
`ai` (manifests `kubernetes/apps/ai/langfuse/app/langfuse.yaml` + `clickhouse.yaml`).
A fresh Trivy scan (2026-08-06, `runbooks/security-check-current.md`) flags two
images with **fixable CRITICAL CVEs**:

- `langfuse/langfuse:3.111.0` — **16 fixable CRITICAL** (CVE-2026-31789,
  CVE-2025-15467, CVE-2025-69421, …). These are base-image / node-dependency CVEs
  that a newer upstream build clears.
- `clickhouse/clickhouse-server:24.1-alpine` — **2 fixable CRITICAL**
  (CVE-2024-6119 [OpenSSL], CVE-2025-26519 [musl libc]). Alpine base-image CVEs;
  a recently-rebuilt tag clears them.

**Why this is held (not auto-safe):** it mutates **two data stores** — langfuse
applies **Postgres + ClickHouse schema migrations automatically on web/worker
startup** ("on start of the application, all migrations are automatically applied
to the databases" — langfuse self-hosting/upgrade docs). Forward-only DB
migrations + a **two-major ClickHouse hop** (24 → 25) on the trace store are not
provably reversible by an image downgrade, so the auto-updater's breaking-change /
data-migration gate correctly holds it for a window. **This is NOT a
false-positive** — it belongs in an operator-present window.

### Target tags — resolved + registry-verified (version-attribution rule)

| Image | Current | Target | Why this tag |
|---|---|---|---|
| `langfuse/langfuse` (web) | 3.111.0 | **3.225.1** | Latest **3.x** (built 2026-08-05, Docker Hub `200`). Stays in major 3 (v4 is a separate data-model migration — out of scope). v3 is security-patched until **end of Jan 2027**. |
| `langfuse/langfuse-worker` | 3.111.0 | **3.225.1** | **MUST match web exactly** (shared migration state). Tag verified present on Docker Hub (`200`). The Trivy finding named only `langfuse/langfuse` (web), but the worker is the same codebase/version and cannot be left behind. |
| `clickhouse/clickhouse-server` | 24.1-alpine | **25.3-alpine** | ClickHouse **LTS**, resolves to `25.3.14.14-alpine`, **rebuilt 2026-02-02** (recent → clears the musl/OpenSSL base CVEs). ≥ 24.3 = langfuse v3's ClickHouse floor. **Below the >25.5.2 "extreme memory on deletion" instability band** (langfuse CH guidance). |

**Rejected ClickHouse candidates (version-attribution evidence):**
- `24.3-alpine` / `24.8-alpine` — rolling tags **last rebuilt 2025-02-19**, i.e.
  *before* the musl (CVE-2025-26519) fix landed in alpine → they do **NOT** clear
  the criticals. Rejected despite being a smaller version hop.
- `25.5-alpine` / `25.6+` / `26.x` — at/above the `>25.5.2` band langfuse warns
  triggers extreme memory usage + instability on deletions. Rejected.
- `25.12+` — only required for langfuse **v4**; unnecessary while we stay on v3.

**Data concern (the crux of the medium rating):** langfuse trace/observation/score
data lives in ClickHouse (`default.*`, tiny — ~2 MiB per the CH maintenance SOP);
users/projects/API-keys live in Postgres. Both get **auto-migrated on startup**,
forward-only. The ClickHouse jump is **two CH majors (24→25)** in one hop — small
single-node dataset makes this low-consequence, but it is an on-disk-format
upgrade, so a Longhorn backup of both PVCs must be fresh before we start, and
**rollback of a failed migration is restore-from-backup, not just an image
downgrade** (see §5).

## 2) Pre-checks

```bash
# a) current state: all langfuse pods Ready, on the expected images, 0 excessive restarts
kubectl get pods -n ai -l 'app in (langfuse-web,langfuse-worker,langfuse-clickhouse,langfuse-postgresql,langfuse-redis,langfuse-zookeeper)' -o wide
kubectl get deploy -n ai langfuse-web       -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'  # langfuse/langfuse:3.111.0
kubectl get deploy -n ai langfuse-worker    -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'  # .../langfuse-worker:3.111.0
kubectl get deploy -n ai langfuse-clickhouse -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}' # clickhouse/clickhouse-server:24.1-alpine

# b) app healthy NOW (baseline so a post-bump failure is attributable)
kubectl exec -n ai deploy/langfuse-web -- wget -qO- localhost:3000/api/public/health   # {"status":"OK"} / 200
CH=$(kubectl get pod -n ai -l app=langfuse-clickhouse -o name | head -1); CH=${CH#pod/}
kubectl exec -n ai "$CH" -- clickhouse-client -q "SELECT version()"                      # 24.1.x
kubectl exec -n ai "$CH" -- clickhouse-client -q "SELECT count() FROM default.observations"  # note this number — must be >= after

# c) BOTH data PVCs have a FRESH Longhorn backup (mandatory before a data-store migration)
kubectl get volumes -n storage -o custom-columns=NAME:.metadata.name,LASTBACKUP:.status.lastBackupAt --no-headers \
  | grep -E 'langfuse-(clickhouse|postgresql)-data'    # both must show a recent lastBackupAt
# If stale, trigger the backup job per docs/sops/backup.md and WAIT for completion before proceeding.

# d) (recommended) shrink the ClickHouse migration surface first — truncate CH system-log
#    telemetry per docs/sops/langfuse-clickhouse-maintenance.md §4 (telemetry only, never default.*):
for t in asynchronous_metric_log metric_log trace_log query_log query_views_log part_log; do
  kubectl exec -n ai "$CH" -- clickhouse-client -q "TRUNCATE TABLE IF EXISTS system.$t"
done

# e) target tags exist in the registry (expect 200 each)
for t in langfuse/langfuse:3.225.1 langfuse/langfuse-worker:3.225.1; do
  curl -s -o /dev/null -w "$t -> %{http_code}\n" "https://hub.docker.com/v2/repositories/${t%%:*}/tags/${t##*:}"; done
curl -s -o /dev/null -w "clickhouse 25.3-alpine -> %{http_code}\n" \
  "https://hub.docker.com/v2/repositories/clickhouse/clickhouse-server/tags/25.3-alpine"

# f) no in-flight reconcile
flux get kustomizations -A | awk 'NR==1 || $5!="True"'
```

## 3) Steps (GitOps, copy-pasteable)

> Three image tags across two files, all in `kubernetes/apps/ai/langfuse/app/`.
> No env/config change is required — CLICKHOUSE_* / DATABASE_URL / S3 wiring all
> carry over. Order matters: **ClickHouse first** (langfuse-web/worker init
> containers `wait-for-clickhouse` on `:9000`, so they hold until CH is back and
> migrated), then langfuse web+worker together.

1. **Silence alerts + active-update marker** (application-update SOP §1) — suppresses
   the expected not-ready blips during the ClickHouse `Recreate` and the langfuse
   rolls, and tells alert-triage the `ai`/langfuse surface is under maintenance:
   ```bash
   runbooks/update-marker.sh add langfuse ai 1 "langfuse 3.111.0->3.225.1 + clickhouse 24.1->25.3-alpine (CVE)"
   ```

2. **Bump ClickHouse** in `kubernetes/apps/ai/langfuse/app/clickhouse.yaml`:
   ```bash
   sed -i '' 's|clickhouse/clickhouse-server:24.1-alpine|clickhouse/clickhouse-server:25.3-alpine|' \
     kubernetes/apps/ai/langfuse/app/clickhouse.yaml
   grep -n 'clickhouse-server:25.3-alpine' kubernetes/apps/ai/langfuse/app/clickhouse.yaml   # exactly one hit
   ```
   > `strategy: Recreate` + RWO PVC means the old CH pod terminates before the new
   > one starts (expected ~1–2 min gap); ClickHouse upgrades the on-disk format in
   > place on first start of 25.3.

3. **Bump langfuse web + worker (lockstep)** in `kubernetes/apps/ai/langfuse/app/langfuse.yaml`:
   ```bash
   sed -i '' 's|image: langfuse/langfuse:3.111.0|image: langfuse/langfuse:3.225.1|' \
     kubernetes/apps/ai/langfuse/app/langfuse.yaml
   sed -i '' 's|image: docker.io/langfuse/langfuse-worker:3.111.0|image: docker.io/langfuse/langfuse-worker:3.225.1|' \
     kubernetes/apps/ai/langfuse/app/langfuse.yaml
   grep -n '3.225.1' kubernetes/apps/ai/langfuse/app/langfuse.yaml   # exactly two hits (web + worker)
   ```

4. **Commit + push** (work on `main`, stage only these two files' hunks):
   ```bash
   git add -p kubernetes/apps/ai/langfuse/app/clickhouse.yaml kubernetes/apps/ai/langfuse/app/langfuse.yaml
   git commit -m "fix(langfuse): CVE bump — langfuse 3.111.0 → 3.225.1, clickhouse 24.1 → 25.3-alpine"
   git push
   ```
   Flux webhook reconciles. ClickHouse Recreates + migrates; langfuse-web/worker
   init containers wait for CH `:9000`, then their startup runs the Postgres +
   ClickHouse langfuse migrations.

5. **On success**, clear the marker (and delete the Alertmanager silence early if
   you set a long TTL):
   ```bash
   runbooks/update-marker.sh clear langfuse
   ```

## 4) Verification

```bash
# a) ClickHouse back on 25.3 and healthy
CH=$(kubectl get pod -n ai -l app=langfuse-clickhouse -o name | head -1); CH=${CH#pod/}
kubectl get pod -n ai "$CH" -o jsonpath='{.spec.containers[0].image}{"\n"}'   # ...:25.3-alpine
kubectl exec -n ai "$CH" -- clickhouse-client -q "SELECT version()"           # 25.3.x
kubectl exec -n ai "$CH" -- clickhouse-client -q "SELECT count() FROM default.observations"  # >= pre-check (b) value

# b) langfuse web + worker rolled onto 3.225.1, Ready, migrations clean
kubectl get deploy -n ai langfuse-web    -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'  # ...:3.225.1
kubectl get deploy -n ai langfuse-worker -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'  # ...:3.225.1
kubectl get pods -n ai -l 'app in (langfuse-web,langfuse-worker)'   # Ready, low restarts
kubectl logs -n ai deploy/langfuse-worker | grep -iE 'migrat|error' | tail -30   # migrations applied, no fatal
kubectl logs -n ai deploy/langfuse-web    | grep -iE 'migrat|error' | tail -30

# c) app end-to-end
kubectl exec -n ai deploy/langfuse-web -- wget -qO- localhost:3000/api/public/health   # 200/OK
# UI reachable via ingress (external class) — https://langfuse.${SECRET_DOMAIN} loads, login works,
# an existing project's traces render (proves ClickHouse data survived the two-major hop).

# d) CVEs actually cleared — re-scan the two images (this is the point of the change)
#    (trivy the running images; expect 0 fixable CRITICAL on both)
#    trivy image langfuse/langfuse:3.225.1
#    trivy image clickhouse/clickhouse-server:25.3-alpine
# Or re-run the security-check sweep and confirm both lines drop off the fixable-CRITICAL list.

# e) Flux + storage sanity
flux get kustomizations -A | awk 'NR==1 || $5!="True"'
kubectl get pvc -n ai | grep langfuse   # both data PVCs Bound
```

Success = both langfuse pods Ready on `:3.225.1` with clean migration logs,
ClickHouse Ready on `25.3-alpine` reporting the same (or higher) `default.observations`
count, `/api/public/health` = 200, UI + existing traces render, and a re-scan shows
the 16 + 2 fixable CRITICALs gone.

## 5) Rollback

**Rollback is version-of-failure dependent — image downgrade alone is NOT
guaranteed safe once forward-only migrations have run.**

- **If langfuse web/worker crash-loops on the new image but ClickHouse is fine and
  no destructive migration completed** — revert the langfuse image bump only:
  ```bash
  git revert --no-edit <commit-sha>     # restores 3.111.0 (both web+worker) + CH 24.1-alpine
  git push
  flux reconcile kustomization -n ai cluster-apps --with-source   # or: flux reconcile source git flux-system
  ```
  Then re-check §4a/c. Because langfuse ran DB migrations targeting 3.225.1,
  **prefer the restore path below** unless startup logs confirm no schema change
  was committed.

- **If ClickHouse fails the 25.3 on-disk upgrade, or langfuse data is
  missing/inconsistent after migration** — this is a **restore-from-backup**, not
  an image downgrade (a partially-migrated store won't cleanly serve the old
  binary):
  1. Scale langfuse-web + langfuse-worker to 0 (`kubectl scale deploy -n ai
     langfuse-web langfuse-worker --replicas=0`) to stop writers.
  2. Revert the git commit (restores CH `24.1-alpine` + langfuse `3.111.0`).
  3. Restore `langfuse-clickhouse-data-new` (and, if Postgres migrated,
     `langfuse-postgresql-data-new`) from the pre-change Longhorn backup taken in
     pre-check (c) — follow `docs/sops/backup.md` restore procedure and the
     shared-storage rules in `docs/sops/storage-safety.md` (**never** `kubectl
     delete pvc` these RWO Longhorn volumes casually).
  4. Scale langfuse back to 1/1, `flux reconcile`, re-verify §4.

Confirm back-to-good: both deployments on `:3.111.0`, CH on `24.1-alpine`,
`/api/public/health` = 200, `default.observations` count matches the pre-check
baseline. Clear the marker (`runbooks/update-marker.sh clear langfuse`).

## 6) Interference notes

- **Blast radius is the langfuse stack inside `ai`, and nothing else.** langfuse
  runs its **own dedicated** Postgres, Redis, ClickHouse, ZooKeeper and MinIO
  (sidecar) — it does **not** touch the cluster-shared Postgres, any shared
  ClickHouse, cert-manager, cilium, coredns, or the Longhorn control plane, so
  `shared: []`. The `external`-class Ingress is a backend endpoint swap only (no
  nginx controller restart) → ingressed apps are unaffected.
- **Ordering within the plan:** bump **ClickHouse first**, then langfuse web+worker.
  The langfuse init containers (`wait-for-clickhouse` on `:9000`) hold web/worker
  until CH is back and migrated, so a slow CH on-disk upgrade parks langfuse in
  Init rather than CrashLoopBackOff. Expect a brief langfuse outage window
  spanning the CH `Recreate` + langfuse migration (budgeted in the 40-min
  estimate).
- **Co-tenant caution (scheduling, not shared data):** OpenClaw and other AI apps
  live in the `ai` namespace but use their **own** storage — no data coupling to
  langfuse. langfuse is an *observability sink*; if OpenClaw/other apps send
  traces to langfuse they'll briefly fail to export during the roll (non-fatal,
  they retry/drop). Still, avoid co-scheduling this with a heavy OpenClaw
  upgrade in the same short window so the two migrations don't compete for node
  resources — not a hard `conflicts_with`, just don't stack them.
- **ClickHouse-specific traps to respect (from the CH maintenance SOP):** do NOT,
  as part of this, add a `<ttl>` to any system-log table with an explicit
  `<engine>` (e.g. `opentelemetry_span_log`) — it aborts CH startup with `Code 36
  BAD_ARGUMENTS` → CrashLoop. This plan changes only the image tag, not the
  `config.d` XML, so that trap is avoided; the note is here so the executor
  doesn't "helpfully" edit the ConfigMap during the same window.
- **Not a reboot job** (`needs_reboot: false`); fits a Tue/Thu/Sat no-reboot slot.
  Operator-present preferred — this mutates two data stores across a two-major
  ClickHouse hop, so someone should be on hand to trigger the restore path if the
  migration goes sideways. Does **not** qualify for the auto-updater (data-store
  migrations are explicitly out of the safe-subset).
