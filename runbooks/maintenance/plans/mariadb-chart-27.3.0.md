---
plan_id: mariadb-chart-27.3.0
component: mariadb
pr: null                              # no Renovate PR; surfaced by the version sweep (F-8ef629f2)
kind: chart
current: "27.0.1"                     # bitnamicharts/mariadb (OCI), appVersion 13.0.1 — HR history re-read live 2026-09-27
target: "27.3.0"                      # appVersion 13.0.1 (UNCHANGED — Chart.yaml of both tarballs, pulled 2026-09-27)
update_type: minor
risk: low                             # chart-only: rendered diff with OUR values = helm.sh/chart label +
                                      # checksum/configuration annotation only (§1.2). Image digest, selector,
                                      # updateStrategy, PVC wiring byte-identical. The one real cost is a
                                      # ~1 min single-pod DB restart under 15 showcase tenants + phpMyAdmin.
est_duration_min: 35                  # §2 dump+baseline 10, §3 push+reconcile 5, restart ~2, §4 verify 15, slack 3
needs_reboot: false
exclusive: false
touches:
  namespaces: [databases, my-software-showcase]
  resources:
    - helmrelease/databases/mariadb               # spec.chart.spec.version only
    - statefulset/databases/mariadb               # pod template changes (label+checksum) => mariadb-0 ROLLS once
    - configmap/databases/mariadb                 # label-only change
    - secret/databases/mariadb                    # label-only; NOTE dual-owned by kustomize(SOPS)+Helm (§6)
    - networkpolicy/databases/mariadb             # template changed upstream, rendered output identical (§1.2)
    - pvc/databases/mariadb-data-5g               # NOT modified; detached/re-attached by the restarted pod (RWO;
                                                  # no nodeSelector/affinity pins it, so it may land on another node)
    - poddisruptionbudget/databases/mariadb       # label-only (helm.sh/chart)
    - serviceaccount/databases/mariadb            # label-only
    - service/databases/mariadb                   # label-only; endpoints empty for the restart gap
    - service/databases/mariadb-headless          # label-only
    - kubernetes/apps/databases/mariadb/app/helmrelease.yaml
    - deployment/databases/phpmyadmin             # read-only consumer; loses its backend for the restart
    - deployments in my-software-showcase (15)    # read-only consumers; readiness flaps on the DB-checking ones,
                                                  # globalmobility + ibgastro liveness is DB-dependent (§1.4)
  shared:
    - shared-mariadb                  # databases/mariadb is itself shared infra: 15 tenant schemas
                                      # + phpMyAdmin. NOT nextcloud (office/nextcloud-mariadb) and NOT
                                      # paperless (office/paperless-db) — both verified live as separate engines.
    - storage/longhorn                # read only: backup freshness check + optional on-demand backup (§2.4)
depends_on: []
conflicts_with:
  - flux-reconciler-impersonation     # exclusive; rewrites how helm-controller applies EVERY HelmRelease,
                                      # touches databases + my-software-showcase. Never the same night.
  - helm-drift-detection              # adds spec.driftDetection to every HR incl. this one; a same-night
                                      # Helm upgrade here muddies its "no upgrade happened" proof.
  - flux-oci-chart-sources            # moves chart sources; the bitnami OCI HelmRepository this HR pulls
                                      # from must not change underneath the bump.
  - app-template-5.2.1                # helm-upgrades phpmyadmin + all 15 my-software-showcase HRs —
                                      # the exact consumer set §4.3 measures; never the same night.
  - chart-patches-coredns-reloader-blackbox  # rolls coredns: the 15 tenants re-resolve
                                      # mariadb.databases.svc when they reconnect after §3.5, so a
                                      # same-night DNS roll confounds the §4.3 reconnect gate.
                                      # No kube-prometheus-stack plan is open (91.4.1 executed): §4 reads
                                      # Prometheus, so a future one MUST be added here (both sides).
capability_change: false              # same server binary (digest pin), same config; the only template
                                      # change is a NetworkPolicy knob whose default preserves behaviour.
rollback_class: git-revert            # no engine/schema change, nothing forward-only. The §2.2 dump is
                                      # insurance, not the rollback path.
security_ref: null
finding_refs:
  - F-8ef629f2                        # "mariadb: chart 27.0.1 → 27.3.0 (minor)" — cycle 58d45ed0
status: vetted    # plan-reviewer 2026-09-28 (F-2c849d1e): needs-fix (app-template-5.2.1 conflict parked) -> fixed -> delta re-review ready-for-go. HUMAN-GATED; needs an operator GO.
review: ready-for-go@2026-09-28
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/mariadb-major-upgrade.md     # dump discipline + marker check (no major here)
  - docs/sops/backup.md
  - docs/sops/longhorn.md
  - docs/sops/storage-safety.md            # no PVC is deleted; cited for the "never delete" boundary
  - docs/sops/verification-contents-not-shape.md
generated: "2026-09-27"
premises:
  # All read-only kubectl get. Values measured live 2026-09-27.
  - id: hr-on-27.0.1-ready
    why: >-
      `current:` claims the HR is on chart 27.0.1 and Ready. If someone already bumped it, or it is
      failing, §3 is a no-op or lands on a broken release. Prints something else and fails.
    run: kubectl get hr -n databases mariadb -o jsonpath='{.spec.chart.spec.version} {.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: 27.0.1 True
  - id: sts-runs-pinned-digest
    why: >-
      The plan's central safety claim is that the server binary does not change. The rendered image
      for 27.3.0 is this exact digest; if the live StatefulSet runs anything else the baseline is wrong.
    run: kubectl get sts -n databases mariadb -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: registry-1.docker.io/bitnami/mariadb@sha256:47bdb03b349e22c62443fa91d95b3f10366aa48ce9e4419990c99b7c23400fa9
  - id: sts-selector-and-strategy
    why: >-
      §1.2 proved the 27.3.0 render keeps this selector (immutable) and RollingUpdate. A live drift
      here means the upgrade could hit "field is immutable" — stop and re-render.
    run: kubectl get sts -n databases mariadb -o jsonpath='{.spec.selector.matchLabels.app\.kubernetes\.io/component},{.spec.selector.matchLabels.app\.kubernetes\.io/instance},{.spec.selector.matchLabels.app\.kubernetes\.io/name},{.spec.selector.matchLabels.app\.kubernetes\.io/part-of} {.spec.updateStrategy.type} {.spec.replicas}'
    expect_exact: primary,mariadb,mariadb,mariadb RollingUpdate 1
  - id: pvc-bound-static
    why: >-
      Data lives on the speaking-name static PV; the chart only references it via existingClaim.
      A rename/re-provision would make the §2.4 backup check look at the wrong volume.
    run: kubectl get pvc -n databases mariadb-data-5g -o jsonpath='{.status.phase} {.spec.storageClassName} {.spec.volumeName} {.spec.accessModes[0]}'
    expect_exact: Bound longhorn-static mariadb-data-5g ReadWriteOnce
  - id: pv-retain
    why: "Rollback insurance: the PV must be Retain so no Helm/Flux prune can take the data with it."
    run: kubectl get pv mariadb-data-5g -o jsonpath='{.spec.persistentVolumeReclaimPolicy}'
    expect_exact: Retain
  - id: longhorn-volume-healthy
    why: "A degraded volume is not the moment to restart the only pod on it; also gates the §2.4 backup."
    run: kubectl get volume -n storage mariadb-data-5g -o jsonpath='{.status.robustness}'
    expect_exact: healthy
  - id: backup-cronjob-exists
    why: >-
      §2.4 reads the nightly Longhorn backup produced by this CronJob (owned by the RecurringJob of the
      same name). Older SOP text names a different object; this is the live one.
    run: kubectl get cronjob -n storage daily-backup-all-volumes -o jsonpath='{.spec.schedule}'
    expect_exact: 0 3 * * *
  - id: phpmyadmin-points-here
    why: "phpMyAdmin is the one in-repo consumer and is used in §4.4; if it moved, drop it from §4."
    run: kubectl get deploy -n databases phpmyadmin -o jsonpath='{.metadata.name}'
    expect_exact: phpmyadmin
---

# mariadb (Bitnami chart) 27.0.1 → 27.3.0

## 1. Summary & why held

Bump `databases/mariadb` HelmRelease `spec.chart.spec.version` from `27.0.1` to
`27.3.0` (Bitnami OCI `oci://registry-1.docker.io/bitnamicharts`). Nothing else.

**Why held:** `runbooks/auto-update-policy.yaml` deny rule `match: "*mariadb*"`,
`max: patch` — *"A DB-engine bump is never unattended-safe. The bitnami
entrypoint can SKIP mariadb-upgrade on a server-major roll…"*. That rule is about
**engine** bumps; this is a chart minor that does **not** change the engine. The
hold is a false positive in substance (see §1.2), which is why `risk: low`. It
still restarts a shared DB, so it belongs in a window, not in Step 0.

### 1.1 Target exists, appVersion unchanged (primary source: the chart tarballs)

```
helm pull oci://registry-1.docker.io/bitnamicharts/mariadb --version 27.0.1   # digest sha256:fe633f4b…
helm pull oci://registry-1.docker.io/bitnamicharts/mariadb --version 27.3.0   # digest sha256:243b7386…
27.0.1/Chart.yaml: appVersion: 13.0.1      27.3.0/Chart.yaml: appVersion: 13.0.1
```

Both embed the same `common` subchart (2.41.0). The published packages carry no
CHANGELOG.md, so the evidence is a full `diff -r` of the two unpacked charts. It
touches exactly four files:

- `Chart.yaml` — version, and the `images` annotation's **mysqld-exporter**
  0.19.0 → 0.20.0 (metrics are not enabled here; nothing renders from it).
- `templates/networkpolicy.yaml` + `values.yaml` + `README.md` — two new knobs:
  `networkPolicy.addExternalClientAccess` (default **true**, wraps the existing
  `<fullname>-client: "true"` podSelector in an `if`, i.e. default = old
  behaviour) and `networkPolicy.ingressReleaseMatchLabels` (default `{}`, adds
  nothing). Both apply only when `networkPolicy.allowExternal` is **false**; ours
  is the chart default `true`, so the `from:` block is not rendered at all.

No breaking change, no migration guide, no values rename.

### 1.2 Rendered diff with OUR values (the thing that actually matters)

`helm template mariadb ./mariadb-<v> -n databases -f <spec.values + dummy auth>`
for both versions, then `diff`:

```
helm.sh/chart: mariadb-27.0.1  ->  mariadb-27.3.0        (8 objects, label only)
checksum/configuration: 2e5795…  ->  de5ae0…             (StatefulSet pod template)
```

That is the entire diff. Consequences:

- **The pod WILL roll once.** Both the pod-template label and the checksum
  annotation change, so `mariadb-0` is recreated (StatefulSet RollingUpdate,
  1 replica ⇒ stop-then-start; StatefulSets are immune to the RWO
  Multi-Attach race in `docs/sops/longhorn-rwo-multi-attach.md`). Measured
  downtime class: tens of seconds to ~1 min.
- **Image stays our digest** — both renders emit
  `registry-1.docker.io/bitnami/mariadb@sha256:47bdb03b…400fa9` (main + init
  container). `app.kubernetes.io/version` stays `13.0.1`.
- **No immutable-field change**: selector identical
  (`component=primary,instance=mariadb,name=mariadb,part-of=mariadb`), no
  `volumeClaimTemplates` in either render (persistence is `existingClaim:
  mariadb-data-5g`), `serviceName` unchanged. `helm upgrade` cannot fail on
  immutability.
- **The legacy `ingress:` values block (F-457e6d05) renders nothing in either
  version** — the Bitnami mariadb chart has no ingress template at all (none
  under `templates/` in 27.0.1 or 27.3.0). Live: zero Ingress objects in
  `databases`. The bump neither fixes nor worsens it; it stays out of scope.

### 1.3 Not 28.x

Latest is 28.0.3, `appVersion: 13.1.1`. Rendering 28.0.3 with our values keeps
our 13.0.1 digest but stamps `app.kubernetes.io/version: 13.1.1` on every
object — the labels would lie about the binary. 28.x must be its own plan:
re-pin the digest to a verified 13.1.x build (Docker Hub version label, per the
HR comment), treat it as an engine change under the deny rule, take the §2.2
dump, and check `/bitnami/mariadb/data/mariadb_upgrade_info` against
`SELECT VERSION()` afterwards (`docs/sops/mariadb-major-upgrade.md`).

### 1.4 Consumers (found live, not from docs)

`information_schema.processlist` at 2026-09-27 12:0x, mapped by pod IP:

- **my-software-showcase** (15 Deployments, each its own `showcase_*_prod`
  schema + `showcase_*_user`): 12 hold persistent connections (Rails pools);
  `globalmobility`, `ibgastro`, `uzeit-de` (PHP) connect per request.
- **databases/phpmyadmin** — `PMA_HOST: mariadb.databases.svc.cluster.local`.
- Also present: `ibTime_demo_companies`, `ibTime_sample_orgs` (no live client),
  empty `my_database`, `test`.
- **Not consumers:** `office/nextcloud` runs its own `StatefulSet/nextcloud-mariadb`;
  `office/paperless-db` is its own `mariadb:12.3.3` Deployment. No other
  HelmRelease values reference `mariadb.databases`.

Probe behaviour against the DB (measured 2026-09-27, response bodies + Rails
`Completed … ActiveRecord: Xms` log lines over the last ~3000 lines per app):

| App(s) | Readiness touches DB? | Liveness touches DB? | DB-touching request used in §4.3 |
|---|---|---|---|
| haarfabrik, holm-backend, inbewegung, max-jung, metaldyne, ordiga, stepbystepguide (Rails) | yes — ActiveRecord 0.1–0.7 ms on every probe | no (`/health/liveness`) | readiness path |
| see-edv-ibspm (Rails) | reports `"database":"ok"` (ActiveRecord 0.0 ms, i.e. a ping, not a query) | no | readiness path |
| kfa-medienarchiv, u-zeit, zuhause-betreut (Rails) | **no** — ActiveRecord 0.0 ms, body `{"status":"ok"}` | no | `GET /login` → 200, ActiveRecord 1.5–2.5 ms |
| mangold-smarthomeadvisor (Rails) | **no** — ActiveRecord 0.0 ms | no | `GET /` → 200, logs `SELECT … FROM changeable_logos` |
| globalmobility (TYPO3 4.2, PHP) | yes — `/health.php` `checks.database` | **YES** — same `/health.php`, period 30 s, failureThreshold 3 | readiness path |
| uzeit-de (TYPO3 6.2, PHP) | yes — `checks.database` names the host | no — `?mode=liveness` checks only `typo3_core` + `install_tool_disabled` | readiness path |
| ibgastro (CakePHP 1.3) | no — `/healthz` on :8080 returns `ok` | **YES** — `/health` on :80 reports `checks.database` (`products: 789`), period 30 s, failureThreshold 3, timeout 5 s | `GET /health` on :80 |

So the DB-reporting readiness endpoints go NotReady for the gap and must come
back; **globalmobility and ibgastro can be RESTARTED by kubelet** if the DB is
gone for ≳90 s (3 × 30 s) — bounded in §4.5. For the four apps whose probes never
query, only an explicit request proves the pool reconnected — §4.3 sends one.

## 2. Pre-checks

Run from the repo root on the Mac mini (zsh). Use a dated work dir:

```bash
cd /Users/mu/code/cberg-home-nextgen
W=~/mariadb-dumps/27.3.0-$(date +%Y%m%d-%H%M%S); mkdir -p "$W"; chmod 700 "$W"; umask 077
.venv/bin/python3 runbooks/plan-premises.py mariadb-chart-27.3.0        # all PASS, else stop
```

**2.1 Flux + workload sane**

```bash
flux get hr -n databases mariadb                     # Ready True, 27.0.1
kubectl -n databases get pod mariadb-0 -o wide       # 1/1 Running
kubectl -n databases get ingress --no-headers 2>&1   # "No resources found" (F-457e6d05 is inert)
```

**2.2 Logical dump (rollback insurance — take it, verify it, keep it)**

Measured 2026-09-27: 4.6 MB, <1 s, 20 `CREATE DATABASE`, ends `-- Dump completed`.
Password comes from the container's own env — never on the Mac command line.

```bash
kubectl -n databases exec mariadb-0 -c mariadb -- sh -c \
  'mariadb-dump -uroot -p"$MARIADB_ROOT_PASSWORD" --protocol=socket --default-character-set=utf8mb4 --all-databases --single-transaction --routines --triggers --events --flush-privileges' \
  > "$W/mariadb-all-pre-27.3.0.sql" 2>"$W/dump.err"
chmod 600 "$W/mariadb-all-pre-27.3.0.sql"
tail -1 "$W/mariadb-all-pre-27.3.0.sql" | grep -q '^-- Dump completed' || { echo "STOP: DUMP INCOMPLETE"; exit 1; }
test "$(grep -c '^CREATE DATABASE' "$W/mariadb-all-pre-27.3.0.sql")" -ge 20 || { echo "STOP: DUMP MISSING SCHEMAS"; exit 1; }
grep -q '^/\*! FLUSH PRIVILEGES \*/;$' "$W/mariadb-all-pre-27.3.0.sql" || { echo "STOP: no FLUSH PRIVILEGES statement in dump"; exit 1; }   # emitted after the mysql schema (measured line 5477 of 50611)
! grep -iv 'password on the command line' "$W/dump.err" || { echo "STOP: dump wrote errors (above)"; exit 1; }
```

Encoding note: user tables are `latin1_swedish_ci` (39), `utf8mb3_general_ci`
(447), `utf8mb3_uca1400_ai_ci` (100) — no utf8mb4 tables, so the SOP's
4-byte-loss trap cannot bite here; `utf8mb4` on the connection is a superset of
all three and is kept per SOP. The dump holds `mysql.global_priv` hashes: `0600`
in a `0700` dir, never committed, delete after the soak (§5.3).

**2.3 Contents baseline — exact per-table row counts, full table set (586 tables)**

```bash
cat > "$W/counts.sh" <<'EOF'
set -e
M="mariadb -uroot -p$MARIADB_ROOT_PASSWORD --protocol=socket -N -B"
$M -e "SET SESSION group_concat_max_len=16777216;
SELECT CONCAT(GROUP_CONCAT(CONCAT('SELECT ''', table_schema, '.', table_name, ''', COUNT(*) FROM \`', table_schema, '\`.\`', table_name, '\`') ORDER BY table_schema, table_name SEPARATOR ' UNION ALL '), ';')
FROM information_schema.tables
WHERE table_type='BASE TABLE'
  AND table_schema NOT IN ('mysql','sys','information_schema','performance_schema');" | $M
EOF
kubectl -n databases exec -i mariadb-0 -c mariadb -- sh -s < "$W/counts.sh" > "$W/counts-T0.tsv" 2>/dev/null
test "$(wc -l < "$W/counts-T0.tsv")" -ge 586 || { echo "STOP: count baseline short/empty"; exit 1; }   # measured 586
awk -F'\t' '{s+=$2} END{print s}' "$W/counts-T0.tsv"    # measured 24850 (must be > 0)
```

`set -e` does NOT protect this pipe: `sh` reports a pipeline's status as the
LAST command's, so if the first `mariadb` (the generator) fails, the second
reads empty input, prints nothing and exits 0. An empty/short output file is
therefore the only failure signal — hence the `wc -l` STOP above and in §4.2.

Record which tenant users hold a connection (the §4.3 baseline):

```bash
kubectl -n databases exec mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" --protocol=socket -N -e "SELECT DISTINCT user FROM information_schema.processlist WHERE user LIKE '"'"'showcase%'"'"' ORDER BY 1;"' \
  2>/dev/null | LC_ALL=C sort > "$W/tenants-T0.txt"   # sort: comm needs byte order; SQL ORDER BY uses the server collation
wc -l < "$W/tenants-T0.txt"      # measured 12 (the 12 Rails apps; the 3 PHP apps connect per request)
```

Also record engine identity and the showcase tenant set:

```bash
kubectl -n databases exec mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" --protocol=socket -N -e "SELECT VERSION(); SELECT COUNT(*) FROM mysql.user; SELECT COUNT(*) FROM information_schema.schemata;"; cat /bitnami/mariadb/data/mariadb_upgrade_info; echo' \
  2>/dev/null > "$W/engine-T0.txt"; cat "$W/engine-T0.txt"
# measured: 13.0.1-MariaDB / 17 / 23 / 13.0.1-MariaDB
kubectl -n databases get pod mariadb-0 -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}' > "$W/imageid-T0.txt"
```

**2.4 Longhorn backup fresh (second insurance layer)**

```bash
kubectl get volume -n storage mariadb-data-5g -o jsonpath='{.status.robustness} {.status.lastBackupAt}{"\n"}'
kubectl -n storage get backups.longhorn.io -l backup-volume=mariadb-data-5g \
  --sort-by=.status.backupCreatedAt -o custom-columns='N:.metadata.name,S:.status.state,AT:.status.backupCreatedAt' | tail -2
```

PASS: `healthy`, newest backup `Completed` and created today at ~03:0x (from
`storage/daily-backup-all-volumes`). `lastBackupAt` can lag one cycle — trust
the newest `Completed` Backup CR (`docs/sops/backup.md`). If none is <24 h old,
take an on-demand backup of `mariadb-data-5g` in the Longhorn UI and wait for
`Completed` before §3.

**2.5 Readiness baseline of all 15 tenants** — save the helper and run it:

```bash
cat > "$W/ready.sh" <<'EOF'
#!/bin/bash
NS=my-software-showcase; P=18100
kubectl -n $NS get deploy -o json | python3 -c '
import sys,json
for d in json.load(sys.stdin)["items"]:
    g=d["spec"]["template"]["spec"]["containers"][0]["readinessProbe"]["httpGet"]
    print(d["metadata"]["name"], g["port"], g["path"])' | while read APP PORT PATHQ; do
  P=$((P+1))
  kubectl -n $NS port-forward deploy/$APP $P:$PORT >/dev/null 2>&1 & PF=$!; sleep 2
  BODY=$(curl -s -m 8 -H 'X-Forwarded-Proto: https' -w '\n%{http_code}' "http://127.0.0.1:$P$PATHQ")
  CODE=$(printf '%s' "$BODY" | tail -n1)
  DB=$(printf '%s' "$BODY" | python3 -c '
import sys,json
raw=sys.stdin.read().rsplit("\n",1)[0]
try: j=json.loads(raw)
except Exception: print("NONJSON:"+raw[:60].replace("\n"," ")); sys.exit()
d=j.get("database") or (j.get("checks") or {}).get("database")
print(json.dumps(d) if d is not None else "NO_DB_FIELD")')
  kill $PF 2>/dev/null; wait $PF 2>/dev/null
  echo "$APP $CODE $DB"
done
EOF
chmod 700 "$W/ready.sh"; "$W/ready.sh" | tee "$W/ready-T0.txt"
```

Measured 2026-09-27: all 15 → `200`; DB field `"connected"` for globalmobility,
haarfabrik, holm-backend, ordiga; `"ok"` for see-edv-ibspm; `{"status": "ok",
"message": "connected to mariadb…"}` for uzeit-de; the other 9 `NO_DB_FIELD` /
`NONJSON`. Any deviation now = stop and investigate first.

**2.6 Silence + marker** (per `application-update.md` Step 1): 2 h silence on
`namespace=~"databases|my-software-showcase"` (namespace-scoped only — the
per-tenant `<App>PodNotReady/PodRestarted/PodCrashLooping` rules and the chart's
`KubeStatefulSet*`/`KubePod*` rules all carry that label);
`runbooks/update-marker.sh add mariadb databases 2 "chart 27.0.1->27.3.0"`.
Rollback retries are NOT disabled: there is no init migration to protect, and
auto-remediation back to 27.0.1 is the desired outcome of a failed upgrade.

## 3. Steps

1. **Edit** (dry-tested on a scratch copy with BSD sed 2026-09-27; the reverse
   edit restores a byte-identical file):

   ```bash
   sed -i '' 's/^\([[:space:]]*version:[[:space:]]*\)27\.0\.1$/\127.3.0/' \
     kubernetes/apps/databases/mariadb/app/helmrelease.yaml
   git diff kubernetes/apps/databases/mariadb/app/helmrelease.yaml
   ```

   Expected diff — exactly one line:
   ```
   -      version: 27.0.1
   +      version: 27.3.0
   ```
   Do NOT touch the `image.digest`, the `ingress:` block (F-457e6d05, separate
   fix) or anything else.

2. **Just before pushing**, take a second count snapshot to measure natural
   write churn: `kubectl -n databases exec -i mariadb-0 -c mariadb -- sh -s < "$W/counts.sh" > "$W/counts-T1.tsv" 2>/dev/null; diff "$W/counts-T0.tsv" "$W/counts-T1.tsv"` — note any tables that moved (tenant writes, expected to be none or few).

3. **Commit + push** (shared worktree rules):

   ```bash
   git commit --only kubernetes/apps/databases/mariadb/app/helmrelease.yaml \
     -m "feat(mariadb): chart 27.0.1 -> 27.3.0 (appVersion 13.0.1 unchanged; plan mariadb-chart-27.3.0)"
   git log -1 --format=%s        # must be YOUR subject; amend before push if not
   git show --stat HEAD          # exactly one file
   git push
   ```

4. **Let Flux reconcile** via the webhook. If the HR has not picked up 27.3.0
   within 5 min, reconcile **Kustomization then HelmRelease** (the order the
   mariadb SOP prescribes; HR-first upgrades with stale values):
   `flux reconcile ks -n databases mariadb && flux reconcile hr -n databases mariadb`.

5. **Watch the roll**: `kubectl -n databases get pod mariadb-0 -w` — expect
   Terminating → ContainerCreating → Running 1/1 within ~2 min. Do not
   hand-delete the pod.

## 4. Verification

**4.1 Release + binary (floor, not the gate)**

```bash
kubectl get hr -n databases mariadb -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion} {.status.history[0].appVersion}{"\n"}'
# PASS: True 27.3.0 13.0.1     FAIL prints False / 27.0.1 (remediated) / anything else
kubectl -n databases get pod mariadb-0 -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}' | diff - "$W/imageid-T0.txt" && echo SAME_DIGEST
# PASS: SAME_DIGEST. A different imageID means the binary changed — this plan is not what ran; go to §5.
kubectl -n databases get pod mariadb-0 -o jsonpath='{.status.startTime} {.status.containerStatuses[0].restartCount}{"\n"}'
# PASS: startTime AFTER the push, restartCount 0. An OLD startTime = the pod did not roll, i.e. the new
# generation never ran (rollout status can green-light the old generation).
```

**4.2 CONTENTS — the data is all still there**

```bash
kubectl -n databases exec -i mariadb-0 -c mariadb -- sh -s < "$W/counts.sh" > "$W/counts-T2.tsv" 2>/dev/null
wc -l < "$W/counts-T2.tsv"                      # must equal T0 (586)
awk -F'\t' '{s+=$2} END{print s}' "$W/counts-T2.tsv"   # must be > 0 and ≈ T1
diff "$W/counts-T1.tsv" "$W/counts-T2.tsv"
```

CONTENTS ASSERTION: every one of the 586 user tables holds the same exact
`COUNT(*)` after the roll as at T1 — measured by `counts.sh` (a generated
`UNION ALL` of `SELECT COUNT(*)` per base table, not `table_rows` estimates),
compared to `counts-T1.tsv`. PASS = empty diff, or only tables that also moved
T0→T1 (tenant writes). FAIL looks like: a table missing (line count < 586), a
schema with all zeros, or `wc -l` = 0 because the server is not accepting root
over the socket (the `2>/dev/null` swallows the error, and the pipe's exit
status is the second `mariadb`'s, so an empty/short file IS the failure signal —
`test "$(wc -l < "$W/counts-T2.tsv")" -ge 586 || echo FAIL`).

```bash
kubectl -n databases exec mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" --protocol=socket -N -e "SELECT VERSION(); SELECT COUNT(*) FROM mysql.user; SELECT COUNT(*) FROM information_schema.schemata;"; cat /bitnami/mariadb/data/mariadb_upgrade_info; echo' \
  2>/dev/null | diff - "$W/engine-T0.txt" && echo ENGINE_SAME
# PASS: ENGINE_SAME (version, 17 users, 23 schemata, marker 13.0.1-MariaDB).
kubectl -n databases exec mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" --protocol=socket -N -e "SELECT @@GLOBAL.sql_mode, @@GLOBAL.init_connect, @@GLOBAL.character_set_server;"' 2>/dev/null
# PASS: NO_ENGINE_SUBSTITUTION	SET NAMES utf8	utf8mb3 — the legacy-compat config the TYPO3/Rails
# tenants need survived the new ConfigMap. Strict mode here = tenant inserts start failing.
```

**4.3 Tenants reconnected (the property this change can silently break)**

Wait 3 min after `mariadb-0` is Ready, then:

```bash
"$W/ready.sh" | tee "$W/ready-T2.txt"; diff "$W/ready-T0.txt" "$W/ready-T2.txt" && echo READY_SAME
```

PASS: `READY_SAME` — all 15 `200`, and the 6 DB-reporting apps show the same
`connected`/`ok` value as T0. FAIL prints e.g. `ordiga 503 "disconnected"` or a
non-200 (measured shape of the healthy response in §2.5; `ordiga`'s endpoint
returns `"database":"connected"` from a live check, `uzeit-de`'s names the host
it reached).

**HARD GATE — every T0 tenant user is connected again.** First send each app
one request that is measured (§1.4 table) to execute SQL, and require `200`:

```bash
cat > "$W/poke.sh" <<'EOF'
#!/bin/bash
# app  target(svc|deploy)  port  path   — paths measured 2026-09-27 to run SQL (§1.4)
NS=my-software-showcase; P=18300; RC=0
while read APP KIND PORT PATHQ; do
  P=$((P+1))
  kubectl -n $NS port-forward $KIND/$APP $P:$PORT >/dev/null 2>&1 & PF=$!; sleep 2
  CODE=$(curl -s -o /dev/null -m 15 -H 'X-Forwarded-Proto: https' -w '%{http_code}' "http://127.0.0.1:$P$PATHQ")
  kill $PF 2>/dev/null; wait $PF 2>/dev/null
  echo "$APP $PATHQ $CODE"; [ "$CODE" = 200 ] || RC=1
done <<'LIST'
haarfabrik svc 3000 /health/readiness
holm-backend svc 3000 /health/readiness
inbewegung svc 3000 /health/readiness
max-jung svc 3000 /health/readiness
metaldyne svc 3000 /health/readiness
ordiga svc 3000 /health/readiness
stepbystepguide svc 3000 /health/readiness
see-edv-ibspm svc 3000 /health/readiness
kfa-medienarchiv svc 3000 /login
u-zeit svc 3000 /login
zuhause-betreut svc 3000 /login
mangold-smarthomeadvisor svc 3000 /
globalmobility svc 80 /health.php
uzeit-de svc 80 /health.php
ibgastro svc 80 /health
LIST
exit $RC
EOF
chmod 700 "$W/poke.sh"; "$W/poke.sh" || echo "FAIL: an app did not answer 200 (listed above)"
kubectl -n databases exec mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" --protocol=socket -N -e "SELECT DISTINCT user FROM information_schema.processlist WHERE user LIKE '"'"'showcase%'"'"' ORDER BY 1;"' \
  2>/dev/null | LC_ALL=C sort > "$W/tenants-T2.txt"
LC_ALL=C comm -23 "$W/tenants-T0.txt" "$W/tenants-T2.txt" > "$W/tenants-missing.txt"
if [ -s "$W/tenants-T2.txt" ] && [ ! -s "$W/tenants-missing.txt" ]; then echo "TENANTS_PASS $(wc -l < "$W/tenants-T2.txt")"; else echo "TENANTS_FAIL missing:"; cat "$W/tenants-missing.txt"; fi
```

PASS: `TENANTS_PASS` with a count ≥ 12 — every user in `tenants-T0.txt` holds
a live connection again (dry-run 2026-09-27 on the healthy cluster: all 15
pokes `200`, same 12 users). There is no "it will reconnect lazily" exception:
the pokes ARE the real requests, so a user still missing after them did not
reconnect. FAIL prints `TENANTS_FAIL missing:` + the user names (an empty
`tenants-T2.txt` — server not answering root over the socket — also FAILs).
On FAIL: map `showcase_<x>_user` to its Deployment, `kubectl -n
my-software-showcase rollout restart deploy/<app>` (pod restart, no manifest
drift), wait for Ready, re-run `poke.sh` and the processlist check. Still
missing after one restart ⇒ §5.1 revert.

Diagnostic only (not a gate — measured: 0 matches over 24 h including the real
`mariadb-0` outage at 08:22Z today, so it cannot fail on its own):

```bash
SINCE=$(kubectl -n databases get pod mariadb-0 -o jsonpath='{.status.startTime}')
for d in $(kubectl -n my-software-showcase get deploy -o name); do
  echo "$d $(kubectl -n my-software-showcase logs "$d" --since-time="$SINCE" 2>/dev/null | \
      grep -ciE "gone away|lost connection|can't connect to (mysql|mariadb|server)|Mysql2::Error|connection refused")"
done
```

**4.4 phpMyAdmin** — `kubectl -n databases port-forward svc/phpmyadmin 18090:80 >/dev/null 2>&1 & PF=$!; sleep 2; curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18090/; kill $PF` → `200` (its login page renders only when the container is up; log in once via the UI if attended and confirm the schema list shows the 15 `showcase_*_prod`).

**4.5 Instruments**

CONTROL: metric kube_statefulset_status_replicas_ready — `{namespace="databases",statefulset="mariadb"}` must read 1 (measured 1 at T0); 0 for more than 5 min after the push = the new pod never became Ready.
CONTROL: metric kube_pod_status_ready — `sum(kube_pod_status_ready{namespace="my-software-showcase",condition="true"})` must return to 15 (measured 15 at T0) within 5 min of `mariadb-0` Ready; the DB-checking tenants (§1.4) drop out during the gap, so a value stuck below 15 names a tenant that did not reconnect.
CONTROL: metric kube_pod_container_status_restarts_total — `increase(kube_pod_container_status_restarts_total{namespace="my-software-showcase",pod!~"globalmobility-.*|ibgastro-.*"}[30m])` must be 0 for every series: those 13 tenants' liveness probes are DB-independent (§1.4), so a non-zero value means one crashed on the lost connection. For `pod=~"globalmobility-.*|ibgastro-.*"` (liveness reads the DB, 3 × 30 s) the bound is ≤ 1 each: expected 0 if the gap stays under ~90 s, 1 is acceptable if it ran longer, and PASS additionally requires that pod to be Ready again (in the `kube_pod_status_ready` sum above) with its `poke.sh` line `200`. ≥ 2 = restart loop ⇒ FAIL.
DIAGNOSTIC (not a gate; absence reading, the restarts CONTROL above is the gate): alertname OrdigaPodCrashLooping — should not be firing 15 min after the roll (representative of the per-tenant `<App>PodCrashLooping` rules in `kube-prometheus-stack/app/*-alerts.yaml`; silenced during the window, so read it from `/api/v1/alerts` state, not from Telegram).
DIAGNOSTIC (not a gate; absence reading): alertname MetaldynePodRestarted — should not be firing (same family; guards the restarts gate above from the alert side).

Delete the silence and clear the marker (`runbooks/update-marker.sh clear mariadb`) once 4.1–4.4 pass.

## 5. Rollback

Nothing in this change is forward-only (same binary, same datadir format, no
schema change), so the primary rollback is a git revert.

**5.1 Revert (any §4 failure):**

```bash
git revert --no-edit <sha-of-§3-commit>
git log -1 --format=%s; git show --stat HEAD          # one file, your subject
git push
flux reconcile ks -n databases mariadb && flux reconcile hr -n databases mariadb   # only if the webhook is slow
```

Confirm: `kubectl get hr -n databases mariadb -o jsonpath='{.status.history[0].chartVersion} {.status.conditions[?(@.type=="Ready")].status}'`
→ `27.0.1 True`; pod rolled again (new startTime), imageID unchanged; re-run
§4.2 counts diff and §4.3 readiness diff against T1/T0 — both must pass.
If Flux's own remediation already rolled back to 27.0.1 (`retries: 3`), still
push the revert so git matches the cluster.

**5.2 If the data is wrong (counts diff unexplained, schema missing):** this
cannot be caused by a label change, so first suspect the wrong volume attached:
`kubectl -n databases get pod mariadb-0 -o jsonpath='{.spec.volumes[?(@.name=="data")].persistentVolumeClaim.claimName}'`
must print `mariadb-data-5g`. If data is genuinely lost, restore from the §2.2 dump
into the running server:

```bash
kubectl -n databases exec -i mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" --protocol=socket --default-character-set=utf8mb4' \
  < "$W/mariadb-all-pre-27.3.0.sql"
```

then re-run §4.2 against `counts-T0.tsv`. Last resort (operator-present only):
restore the §2.4 Longhorn backup (newest `Completed` Backup CR for
`mariadb-data-5g`) following the restore procedure in `docs/sops/backup.md`.
**Never delete the PVC or PV** (`docs/sops/storage-safety.md`; PV is `Retain`).

**5.3 Cleanup:** after 7 clean days, `rm -rf "$W"` (dump contains password hashes).

## 6. Interference notes

- **Shared DB restart.** `mariadb-0` goes away for ~1 min. That takes 15
  showcase tenants' DB and phpMyAdmin with it. None of the household services
  (nextcloud, paperless, authentik, HA) use this instance — verified live
  (`office/nextcloud-mariadb`, `office/paperless-db` are separate engines; no
  other HR references `mariadb.databases`).
- **Do not co-schedule with `paperless-db-13.0.2` just because both say
  "mariadb"** — no shared object, no conflict; they may share a window.
- **Dual-owned Secret.** `secret/databases/mariadb` is applied by kustomize
  (SOPS, 4 keys) AND rendered by the chart (Helm ownership annotations, 2 keys).
  This has survived 14 Helm revisions and the bump changes only its
  `helm.sh/chart` label, but if §4 shows auth failures, check the Secret still
  has all four keys (`mariadb-database mariadb-password mariadb-root-password
  mariadb-user`) before anything else — the HR's `valuesFrom` reads them.
- `conflicts_with`: `flux-reconciler-impersonation` (exclusive; changes how the
  HR is applied, touches both namespaces), `helm-drift-detection` (adds a field
  to this HR), `flux-oci-chart-sources` (could move the chart source),
  `chart-patches-coredns-reloader-blackbox` (coredns roll during tenant
  reconnects confounds §4.3), `app-template-5.2.1` (helm-upgrades phpMyAdmin
  and all 15 showcase HRs — the §4.3 consumer set). The scheduler honours
  these symmetrically; the other plans should still list this one back.
- §4.5 reads Prometheus; no kube-prometheus-stack plan is open. If one is
  written, it goes into `conflicts_with` on both sides.
- No reboot, no node drain, no Longhorn engine change.
- The legacy `ingress:` block (F-457e6d05) is untouched and remains inert with
  27.3.0; fix it in its own commit, not inside this bump (keeps the revert
  surface to one line).
