---
plan_id: mariadb-28.1.1
component: mariadb
pr: null                              # no Renovate PR; surfaced by coverage.py needs_plan_groups (group_kind single)
kind: chart
current: "27.3.0"                     # bitnamicharts/mariadb (OCI), appVersion 13.0.1, image digest-pinned to 13.0.1
                                      # (re-measured live 2026-10-05: HR 27.3.0 Ready, chart history 27.3.0/13.0.1,
                                      # SELECT VERSION() 13.0.1-MariaDB, marker 13.0.1, mariadb-0 started
                                      # 2026-10-03T19:35Z = the 0ddd0b54 roll, restartCount 0)
target: "28.1.1"                      # appVersion 13.1.1 — chart + image digest re-pin to a VERIFIED 13.1.1 build,
                                      # in lockstep (§1.2). Chart-only would leave 13.0.1 running under 13.1.1 labels.
update_type: major                    # chart major; carries the server release-series change 13.0 -> 13.1
risk: high                            # one-way system-table conversion of a SHARED DB (4 showcase tenants +
                                      # 2 ibTime_* schemas + phpMyAdmin; 11 tenants decommissioned 2026-10-04)
                                      # AND an upstream default change (utf8 -> utf8mb4) that silently changes
                                      # the legacy-compat charset config those tenants depend on (§1.3). The
                                      # entrypoint's own upgrade step is BROKEN (§1.4) so a manual step is mandatory.
est_duration_min: 55                  # §2 dump+proofs+baselines 20, §3 push/roll/upgrade 10, §4 verify 20, slack 5.
                                      # The §5.2 snapshot-revert rollback adds ~35 (operator at the Longhorn UI);
                                      # place it where ~90 min FREE exists (sun-attended preferred).
needs_reboot: false
exclusive: false
touches:
  namespaces: [databases, my-software-showcase, storage]
  resources:
    - kubernetes/apps/databases/mariadb/app/helmrelease.yaml   # chart version, image digest, comment, my.cnf old_mode,
                                                               # upgrade.remediation.retries 3->0 (restored in §3.9)
    - helmrelease/databases/mariadb
    - statefulset/databases/mariadb               # pod template: image digest + labels + checksum => mariadb-0 ROLLS
    - configmap/databases/mariadb                 # my.cnf gains old_mode=UTF8_IS_UTF8MB3
    - secret/databases/mariadb                    # label-only; dual-owned kustomize(SOPS)+Helm (§6)
    - service/databases/mariadb                   # label-only; endpoints empty during the roll
    - service/databases/mariadb-headless          # label-only
    - networkpolicy/databases/mariadb             # label-only
    - poddisruptionbudget/databases/mariadb       # label-only
    - serviceaccount/databases/mariadb            # label-only
    - pvc/databases/mariadb-data-5g               # system tables converted IN PLACE by mariadb-upgrade (one-way)
    - volumesnapshot/databases/mariadb-data-pre-13-1   # created in §2.6 (backup_gate); kept until §5.4 cleanup
    - pod/databases/mariadb-restoretest           # scratch pod for restore_proof (§2.5), deleted in the same step
    - volume.longhorn.io/storage/mariadb-data-5g  # snapshot created; reverted only on §5.2
    - deployment/databases/phpmyadmin             # consumer; loses its backend for the roll
    - deployment/my-software-showcase/haarfabrik  # consumers (Rails, persistent pool); DB-aware readiness flaps,
    - deployment/my-software-showcase/metaldyne   # liveness is tcpSocket :3000 since f515915c, so a bounce should
    - deployment/my-software-showcase/u-zeit      # not restart them (bound <=1 kept per maintenance-windows.md s7)
    - deployment/my-software-showcase/uzeit-de    # consumer (PHP, per-request connections)
  shared:
    - shared-mariadb                  # databases/mariadb IS shared infra: 4 showcase schemas + 2 ibTime_* + phpMyAdmin.
                                      # NOT nextcloud (office/nextcloud-mariadb) and NOT paperless (office/paperless-db).
    - storage/longhorn                # in-window VolumeSnapshot; snapshot revert on rollback
    - monitoring                      # §4.5 reads Prometheus
depends_on: []
conflicts_with:
  # shared-infra / same-object guards (carried from the executed mariadb-chart-27.3.0; every id re-checked
  # against load_plans() 2026-10-05 — all still open)
  - flux-reconciler-impersonation     # exclusive; changes how helm-controller applies this HR
  - helm-drift-detection              # adds spec.driftDetection to this HR
  - flux-oci-chart-sources            # moves the bitnami OCI source this HR pulls 28.1.1 from
  - flux-fleet-0.60.0                 # restarts helm-controller mid-upgrade; retries:0 makes a half-applied release sticky
  - app-template-5.2.1                # helm-upgrades phpMyAdmin + all 4 showcase HRs = the §4.3 consumer set
  - chart-patches-coredns-reloader-blackbox  # coredns roll confounds the tenant-reconnect gate
  - coredns-1.48.1                    # same reason
  - longhorn-1.13.0                   # storage engine move under a snapshot + in-place conversion
  - jellyfin-config-rwo-migration     # hands-on Longhorn volume work + its own restore-test; same storage/longhorn surface as the §2.6 snapshot / §5.2 revert (review 2026-10-05)
  - talos-linux-1.14.2                # node roll would evict mariadb-0 / detach the volume mid-procedure
  - kube-prometheus-stack-91.9.0      # exclusive; restarts Prometheus, which §4.5 reads (it already lists this plan)
  # ROLLBACK-CLASS STACKING (convention from paperless-db-13.0.2): two backup-restore rollbacks in one slot
  # leave no rollback capacity for either. Every live backup-restore plan, read via load_plans() 2026-10-05:
  - talos-sysfs-power-caps            # backup-restore (now:2026-10-05, awaiting-soak); added 2026-10-05
  - paperless-db-13.0.2
  - bitnamilegacy-exit-nextcloud-db
  - nextcloud-fleet-35.0.1
  - nocodb-2026.09.1                  # also namespace databases; its dead mariadb-chart-27.3.0 ref was retargeted to this plan 2026-10-04
  - n8n-2.39.8
  - jellyfin-12.1
  - media-naming-p3
  - penpot-chart-1.10.0
  # talconfig-multidoc-migration: EXECUTED now:2026-10-04 and retired (10bee773); dead ref removed 2026-10-05 (sweep 481b9c1f)
  # kube-prometheus-stack-91.9.0 (draft, d8ecdb2e) is listed above; §4.5 reads Prometheus.
capability_change: false              # same service, same tenant-visible behaviour: the one default that would change
                                      # behaviour (utf8 = utf8mb4) is pinned back by old_mode (§1.3) and asserted in §4.2.
                                      # 13.1's new SQL features are unused by any tenant.
rollback_class: backup-restore        # NOT git-revert: mariadb-upgrade rewrites mysql.* system tables for 13.1; a
                                      # revert alone points a 13.0.1 binary at them. §5.2 = quiesced Longhorn snapshot
                                      # revert, §5.3 = logical dump restore.
backup_gate: "TWO artifacts, both BEFORE the §3 push: (a) logical dump of --all-databases from the LIVE 13.0.1 pod over the socket with --default-character-set=utf8mb4, proven by the fail-closed §2.4 script under set -euo pipefail (exits non-zero on a missing '-- Dump completed' trailer, <9 CREATE DATABASE, no FLUSH PRIVILEGES, any dump stderr, or <1 MB); (b) VolumeSnapshot mariadb-data-pre-13-1 (class longhorn-snapshot) readyToUse=true with its snap:// handle recorded to $W/snaphandle.txt (§2.6) — the PRIMARY rollback artifact"
restore_proof: "§2.5: the §2.4 dump is loaded into a scratch pod mariadb-restoretest running the ROLLBACK binary (same 13.0.1 digest, emptyDir datadir, root password from secret/mariadb), and the exact per-table COUNT(*) of all 212 user tables must equal counts-T0.tsv (diff empty, line count >= 212) and the 4 showcase_* users must be present in mysql.global_priv (both asserted by the §2.5 script). Pod deleted afterwards. A dump that exists is not a dump that restores."
security_ref: null                    # version-currency driver, not a security driver
finding_refs:
  - F-1fa39efd                        # chart 27.3.0 -> 28.1.1 version finding (sweep 481b9c1f, 2026-10-05); supersedes
                                      # F-8ef629f2, auto-closed when the 27.3.0 row executed
  - F-8ef629f2                        # predecessor version finding (27.0.1->27.3.0), status resolved 2026-10-03
  - F-9ab5f80f                        # restart-gate template (resolved 2026-10-04 by f515915c + a6bf8413); §4.3/§4.5
                                      # implement it here: restart bound <=1, processlist baseline = 3 Rails pool users
status: draft
review: null
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/mariadb-major-upgrade.md     # dump discipline, socket-only upgrade; two stale claims, see §1.4
  - docs/sops/backup.md
  - docs/sops/longhorn.md
  - docs/sops/storage-safety.md            # no PVC/PV is deleted on any path
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-04"
regenerated: "2026-10-05"            # re-planned after the 2026-10-04 showcase decommission (11 tenants dropped)
premises:
  # All read-only. Values measured live 2026-10-04, re-measured 2026-10-05 after the showcase decommission.
  - id: hr-on-27.3.0-ready
    why: >-
      current claims chart 27.3.0 and Ready. If already bumped or failing, §3 lands on a broken release.
    run: kubectl get hr -n databases mariadb -o jsonpath='{.spec.chart.spec.version} {.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: 27.3.0 True
  - id: sts-runs-13.0.1-digest
    why: >-
      The baseline and the restore_proof binary are this digest. Anything else means the plan describes a
      different starting point.
    run: kubectl get sts -n databases mariadb -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: registry-1.docker.io/bitnami/mariadb@sha256:47bdb03b349e22c62443fa91d95b3f10366aa48ce9e4419990c99b7c23400fa9
  - id: hr-history-appversion-13.0.1
    why: >-
      The running release is the 13.0.1 app line. (Marker, live VERSION() and old_mode need kubectl exec,
      which the premise runner refuses; they are asserted as STOP checks in §2.3 instead.)
    run: kubectl get hr -n databases mariadb -o jsonpath='{.status.history[0].appVersion}'
    expect_exact: 13.0.1
  - id: mycnf-has-no-old-mode-yet
    why: >-
      §3 ADDS old_mode=UTF8_IS_UTF8MB3 after the init_connect line. If the rendered my.cnf already carries an
      old_mode line, someone changed the config and the §3 sed would duplicate it. Prints 1+ on drift.
    run: kubectl get cm mariadb -n databases -o jsonpath='{.data.my\.cnf}' | grep -c old_mode
    expect_exact: "0"
  - id: mycnf-init-connect-anchor
    why: "The §3 sed anchors on this exact line; 0 means the edit would silently add nothing."
    run: kubectl get cm mariadb -n databases -o jsonpath='{.data.my\.cnf}' | grep -c 'init_connect="SET NAMES utf8"'
    expect_exact: "1"
  - id: chart-28.1.1-appversion
    why: "The target chart must exist and still carry appVersion 13.1.1 (labels must match the pinned binary)."
    run: "helm show chart oci://registry-1.docker.io/bitnamicharts/mariadb --version 28.1.1 | grep '^appVersion'"
    expect_exact: "appVersion: 13.1.1"
  - id: pvc-bound-static
    why: "Data lives on the speaking-name static PV; the snapshot and the revert target this exact volume."
    run: kubectl get pvc -n databases mariadb-data-5g -o jsonpath='{.status.phase} {.spec.storageClassName} {.spec.volumeName} {.spec.accessModes[0]}'
    expect_exact: Bound longhorn-static mariadb-data-5g ReadWriteOnce
  - id: pv-retain
    why: "Rollback insurance: no Helm/Flux prune can take the data with it."
    run: kubectl get pv mariadb-data-5g -o jsonpath='{.spec.persistentVolumeReclaimPolicy}'
    expect_exact: Retain
  - id: longhorn-volume-healthy
    why: "A degraded volume is not the moment to snapshot, convert and possibly revert it."
    run: kubectl get volume -n storage mariadb-data-5g -o jsonpath='{.status.robustness}'
    expect_exact: healthy
  - id: snapshot-class-exists
    why: "§2.6 backup_gate (b) creates a VolumeSnapshot of this class; the §5.2 revert keys on it."
    run: kubectl get volumesnapshotclass longhorn-snapshot -o jsonpath='{.driver}'
    expect_exact: driver.longhorn.io
  - id: backup-cronjob-exists
    why: "§2.7 reads the nightly Longhorn backup from this CronJob (older SOP text names a different object)."
    run: kubectl get cronjob -n storage daily-backup-all-volumes -o jsonpath='{.spec.schedule}'
    expect_exact: 0 3 * * *
  - id: phpmyadmin-exists
    why: "phpMyAdmin is checked in §4.4."
    run: kubectl get deploy -n databases phpmyadmin -o jsonpath='{.metadata.name}'
    expect_exact: phpmyadmin
  - id: four-showcase-tenants
    why: >-
      §4.3 pokes exactly these 4 apps (11 were decommissioned 2026-10-04). Prints a different list if a tenant
      was added or removed since, i.e. the consumer list is stale.
    run: kubectl get deploy -n my-software-showcase --no-headers -o custom-columns=N:.metadata.name | sort | tr '\n' ' '
    expect_exact: "haarfabrik metaldyne u-zeit uzeit-de"
  - id: rails-liveness-tcpsocket
    why: >-
      The <=1 restart bound in §4.3 assumes the f515915c fix: Rails liveness is tcpSocket :3000, so a DB bounce
      cannot fail it. Prints an httpGet/empty value if the fix was reverted.
    run: kubectl get deploy -n my-software-showcase haarfabrik metaldyne u-zeit -o jsonpath='{range .items[*]}{.spec.template.spec.containers[0].livenessProbe.tcpSocket.port} {end}'
    expect_exact: "3000 3000 3000"
---

# mariadb (Bitnami chart) 27.3.0 → 28.1.1 — server 13.0.1 → 13.1.1

## 1. Summary & why held

Bump `databases/mariadb` chart `27.3.0 → 28.1.1` **and** re-pin the image
digest from the 13.0.1 build to the 13.1.1 build, add one `my.cnf` line that
keeps today's charset semantics, run `mariadb-upgrade` by hand, and prove the
4 remaining showcase tenants (haarfabrik, metaldyne, u-zeit, uzeit-de), the
2 `ibTime_*` schemas and phpMyAdmin still work against the same data.

**Why held:** `runbooks/auto-update-policy.yaml` deny rule for `*mariadb*` —
*"A DB-engine bump is never unattended-safe. The bitnami entrypoint can SKIP
mariadb-upgrade on a server-major roll…"*. Unlike 27.3.0 (a false positive:
same engine), this hold is **correct**: 28.x is exactly the engine change the
rule describes, and §1.3/§1.4 found two further traps.

### 1.1 What the chart major actually contains (primary source: the tarballs)

`helm pull oci://registry-1.docker.io/bitnamicharts/mariadb --version {27.3.0,28.0.3,28.1.1}`
(digests `243b7386…`, `53cb3d64…`, `ac018be0…`), `diff -r` 27.3.0 ↔ 28.1.1:

- `Chart.yaml`: `appVersion 13.0.1 → 13.1.1` (and the images annotation). Same
  `common` 2.41.0. The chart major is Bitnami's convention for an app
  release-series bump. The README has no "To 28.0.0" upgrade note.
- `templates/{primary,secondary}/statefulset.yaml` + `values.yaml`: one new
  knob `primary.enableServiceLinks`, default `true` = the Kubernetes default,
  so behaviour is unchanged.
- **No values renames, no auth/secret key changes, no selector change.** Image
  source unchanged: `registry-1.docker.io/bitnami/mariadb` (default `tag:
  latest`, `digest: ""`). This is **not** a bitnamilegacy move, because our
  values already override `image.digest`.

Rendered with OUR values (`helm template`; 27.3.0 + current values vs 28.1.1 +
the §3 values), the full diff is: `app.kubernetes.io/version 13.0.1→13.1.1` +
`helm.sh/chart` on 8 objects, the image digest on main + init container,
`checksum/configuration`, one added `old_mode=UTF8_IS_UTF8MB3` line in the
ConfigMap, and `enableServiceLinks: true` rendered explicitly. The selector
(`component=primary,instance=mariadb,name=mariadb,part-of=mariadb`), the
`existingClaim: mariadb-data-5g` and `serviceName` are identical, so the
upgrade cannot fail on immutable fields.

### 1.2 Why chart + digest in lockstep (not chart-only)

Our values pin `image.digest` (HR comment: Bitnami's free tier publishes no
semver tags). Chart-only 28.1.1 would keep running the 13.0.1 binary while
stamping `13.1.1` on every object. That is the labels lying, which the 27.3.0
plan §1.3 already rejected. So the target digest is the current `latest` index
**`sha256:354e5aec…037e`**, verified from the registry 2026-10-04: amd64 child
`sha256:b1aa4edf…`, config label `org.opencontainers.image.version=13.1.1`,
`APP_VERSION=13.1.1`, created 2026-09-30, base `photon:5.0`. The §2.0
exec-only check (`TARGET_DIGEST_OK`) re-checks it at runtime. The current pin
`47bdb03b…` (amd64 `1a9e52dd…`, label 13.0.1) still resolves. It is also the
rollback binary.

### 1.3 The breaking change: `utf8` now means `utf8mb4` (upstream, 13.1)

MariaDB docs, OLD_MODE: *"From MariaDB 13.1, `UTF8_IS_UTF8MB3` is no longer
set by default. The default `old_mode` is now empty, so `utf8` is an alias for
`utf8mb4` by default."* The flag still works but is deprecated (it logs a
deprecation warning). 13.1 changes-and-improvements: *"The default `utf8`
character set is now `utf8mb4`."*
(https://mariadb.com/docs/server/server-management/variables-and-modes/old_mode,
https://mariadb.com/docs/release-notes/community-server/13.1/mariadb-13.1-changes-and-improvements)

Our `primary.configuration` is the legacy-compat block written for the
TYPO3 4.2 / Rails 3.2 tenants. Every charset line in it says `utf8`:
`character-set-server=UTF8`, `collation-server=utf8_general_ci`,
`init_connect="SET NAMES utf8"`, `[client] default-character-set=UTF8`. Live
today: `@@old_mode = UTF8_IS_UTF8MB3`, `character_set_server = utf8mb3`,
`collation_server = utf8mb3_general_ci`. Re-measured 2026-10-05 (after the
2026-10-04 decommission dropped 11 tenants, which took every `latin1` table
with them): all 212 user tables are `utf8mb3` (166 `utf8mb3_general_ci`, 46
`utf8mb3_uca1400_ai_ci`), and there are **zero utf8mb4 tables**.

Under a 13.1 binary with the config unchanged, the same text would silently
become `utf8mb4` server defaults, and `init_connect` would force
`SET NAMES utf8mb4`. That reverses the exact mb3 forcing the HR comment says
TYPO3 4.2 needs, because it string-compares the charset name. Any client-side
`SET NAMES utf8` from the Rails 3.2 apps would change meaning too.
Nothing errors, every count matches, and the apps change behaviour.

**Remedy in this plan:** add `old_mode=UTF8_IS_UTF8MB3` to `[mysqld]`. That
restores exactly today's semantics for every place the string `utf8` appears,
server-side and from clients. We use it instead of rewriting the four lines to
`utf8mb3`, because only `old_mode` also covers the tenants' own `SET NAMES
utf8` statements. The cost is a deprecation warning in the log, plus a
follow-up owed before the flag is removed upstream (§6). §4.2 asserts the
effect directly: `SELECT CHARSET(CONVERT('x' USING utf8))` must return
`utf8mb3`. Without the line, 13.1 returns `utf8mb4`.

Other 13.1 items reviewed and judged irrelevant for a standalone server with
these tenants: DENY grants and new JSON operators (new syntax, which changes
the `mysql.*` privilege tables and confirms `mariadb-upgrade` is needed),
replication domain-id validation, mariadb-dump generated-column handling (our
dump is taken with the 13.0.1 client), and short-circuit AND/OR evaluation.
13.1 is a **rolling** release, like the 13.0 line we are on.

### 1.4 The entrypoint never runs mariadb-upgrade (root cause, measured)

The policy text says the entrypoint "can" skip the upgrade. In fact it
**always** skips it. Read live in the running 13.0.1 image:
`/opt/bitnami/scripts/libmariadb.sh:538` runs
`"${DB_BIN_DIR}/mariadb_upgrade" … || info "This installation is already upgraded"`,
with `DB_BIN_DIR=/opt/bitnami/mariadb/bin`. That directory holds
`mariadb-upgrade` (hyphen) and the symlink `mysql_upgrade`, but **no
`mariadb_upgrade`** (`command -v` finds nothing). The call fails with
not-found, and the `||` turns the failure into the reassuring log line seen on
every start, including the current pod (`19:35:42 … This installation is
already upgraded`). That fully explains the 12→13 incident. So in §3.7 the
manual `mariadb-upgrade --protocol=socket --skip-ssl` is a **mandatory step,
not a contingency**. If a future Bitnami build fixes the name, the manual run
is a harmless no-op (it reports the installation is already upgraded and the
marker already matches).

(Repo corrections in the report: the SOP's verification command reads
`/bitnami/mariadb/data/mysql_upgrade_info`, but the live file is
`mariadb_upgrade_info`; and the SOP's "can skip" wording should name this
root cause.)

### 1.5 Consumers (live, 2026-10-04)

- **Decommission, 2026-10-04:** eleven showcase apps were removed and their
  databases and users dropped (globalmobility, holm, ibgastro, inbewegung,
  kfa_medienarchiv, mangold, max_jung, ordiga, see_edv, stepbystepguide,
  zuhause_betreut). This plan was re-measured against what is left
  (2026-10-05): 12 schemata, 6 accounts in `mysql.user`, 212 user base tables,
  2434 rows in total, dump 3.17 MB with 9 `CREATE DATABASE`.
- **my-software-showcase**: 4 Deployments, all `strategy: Recreate`. Schemas
  `showcase_{haarfabrik,metaldyne,u_zeit,uzeit_de}_prod`. The processlist holds
  exactly **3 Rails pool users**
  (`showcase_{haarfabrik,metaldyne,u_zeit}_user`, 4/2/2 sleeping connections).
  The PHP app uzeit-de connects per request, so its user is absent between
  requests and is kept out of the tenant baseline (maintenance-windows.md §7).
- **`ibTime_demo_companies`, `ibTime_sample_orgs`** (23 tables each) and
  `my_database`, `test`: no dedicated account, no connected client. They are
  covered by the counts, dump and restore gates, not by a poke.
- Probe map (live 2026-10-05): the 3 Rails tenants have liveness
  `tcpSocket :3000` since **f515915c** (F-9ab5f80f root-cause fix), with
  readiness `httpGet /health/readiness` (DB-aware). uzeit-de has liveness
  `httpGet /health.php?mode=liveness` and readiness `/health.php`. uzeit-de
  was NOT restarted by the 2026-10-03 bounce (startTime 2026-09-28,
  restartCount 0). The Rails pods were re-created 2026-10-04 07:02Z by
  f515915c and all four have restartCount 0 now.
  History (F-9ab5f80f): on 2026-10-03, with the old `httpGet` liveness,
  single-threaded WEBrick starved on DB-blocked readiness calls and 5 Rails
  tenants restarted once. With `tcpSocket` liveness the expected delta is now
  **0**. The gate still allows **<= 1** per consumer during the bounce and
  fails on a second restart (SOP rule). Every restart gate below is a
  **delta** from T0.
- **databases/phpmyadmin** (`PMA_HOST mariadb.databases.svc`).
- Not consumers: `office/nextcloud-mariadb`, `office/paperless-db` (separate
  engines), and nothing in household services.

## 2. Pre-checks

From the repo root on the Mac mini. One work dir for the whole plan. **Every
later step reuses `$W`. If you open a new shell, re-export it from
`$HOME/mariadb-dumps/LATEST` first.**

```bash
cd /Users/mu/code/cberg-home-nextgen
W=$HOME/mariadb-dumps/28.1.1-$(date +%Y%m%d-%H%M%S); mkdir -p "$W"; chmod 700 "$W"; umask 077
ln -sfn "$W" "$HOME/mariadb-dumps/LATEST"          # new shell: W=$(readlink "$HOME/mariadb-dumps/LATEST")
.venv/bin/python3 runbooks/plan-premises.py mariadb-28.1.1     # all PASS, else STOP
```

**2.0 Exec-only premises** (the premise runner refuses `kubectl exec` and
`python3`, so these run here; each prints a different value on drift):

```bash
kubectl -n databases exec mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" --protocol=socket -N -e "SELECT VERSION(), @@GLOBAL.old_mode, @@GLOBAL.character_set_server"; cat /bitnami/mariadb/data/mariadb_upgrade_info' \
  2>/dev/null | tr '\n\t' '  ' | tee "$W/pre-engine.txt"; echo
grep -qx '13.0.1-MariaDB UTF8_IS_UTF8MB3 utf8mb3 13.0.1-MariaDB ' "$W/pre-engine.txt" || { echo "STOP: engine/marker/old_mode not as measured 2026-10-04"; exit 1; }
# Target digest resolves (amd64) to an image labelled 13.1.1 — prints another version or a traceback otherwise
python3 -c "import json,urllib.request as u
R='https://registry-1.docker.io/v2/bitnami/mariadb/'
t=json.load(u.urlopen('https://auth.docker.io/token?service=registry.docker.io&scope=repository:bitnami/mariadb:pull'))['token']; A='Bearer '+t
ix=json.load(u.urlopen(u.Request(R+'manifests/sha256:354e5aec20455bce931a05fa791c51e4a45879015bee09591295c76fe88c037e',headers={'Authorization':A,'Accept':'application/vnd.docker.distribution.manifest.list.v2+json,application/vnd.oci.image.index.v1+json'})))
d=[m['digest'] for m in ix['manifests'] if m['platform']['architecture']=='amd64'][0]
c=json.load(u.urlopen(u.Request(R+'manifests/'+d,headers={'Authorization':A,'Accept':'application/vnd.docker.distribution.manifest.v2+json,application/vnd.oci.image.manifest.v1+json'})))['config']['digest']
print(json.load(u.urlopen(u.Request(R+'blobs/'+c,headers={'Authorization':A})))['config']['Labels']['org.opencontainers.image.version'])" \
  | grep -qx '13.1.1' && echo TARGET_DIGEST_OK || { echo "STOP: target digest is not 13.1.1 (or unreachable)"; exit 1; }
```

**2.1 Flux + workload sane**

```bash
flux get hr -n databases mariadb                     # Ready True, 27.3.0
kubectl -n databases get pod mariadb-0 -o wide       # 1/1 Running
```

**2.2 Silence + marker** (per `application-update.md`). Set a 2 h silence on
`namespace=~"databases|my-software-showcase"`, then run
`runbooks/update-marker.sh add mariadb databases 2 "chart 27.3.0->28.1.1, server 13.0.1->13.1.1"`.

**2.3 Baselines (T0)**: counts, engine identity, tenants, restart counts.

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
test "$(wc -l < "$W/counts-T0.tsv")" -ge 212 || { echo "STOP: count baseline short/empty"; exit 1; }   # measured 212 (2026-10-05)
awk -F'\t' '{s+=$2} END{print s}' "$W/counts-T0.tsv"      # must be > 0
```

`set -e` does not protect the pipe. If the generator fails, the second
`mariadb` reads empty input and exits 0. A short or empty file is the failure
signal, hence the `wc -l` STOP.

```bash
cat > "$W/engine.sh" <<'EOF'
mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" --protocol=socket -N -B -e "
SELECT COUNT(*) FROM mysql.user;
SELECT COUNT(*) FROM information_schema.schemata;
SELECT CONCAT(user,'@',host) FROM mysql.user ORDER BY 1;
SELECT @@GLOBAL.sql_mode, @@GLOBAL.init_connect, @@GLOBAL.character_set_server, @@GLOBAL.collation_server;
SELECT CHARSET(CONVERT('x' USING utf8));
SELECT table_collation, COUNT(*) FROM information_schema.tables WHERE table_schema NOT IN ('mysql','sys','information_schema','performance_schema') AND table_collation IS NOT NULL GROUP BY 1 ORDER BY 1;" 2>/dev/null
EOF
kubectl -n databases exec -i mariadb-0 -c mariadb -- sh -s < "$W/engine.sh" > "$W/engine-T0.txt"
cat "$W/engine-T0.txt"
# measured 2026-10-05: 6 / 12 / 6 user@host lines / NO_ENGINE_SUBSTITUTION SET NAMES utf8 utf8mb3 utf8mb3_general_ci /
# utf8mb3 / utf8mb3_general_ci 166, utf8mb3_uca1400_ai_ci 46
grep -qx 'utf8mb3' "$W/engine-T0.txt" || { echo "STOP: CONVERT(... USING utf8) is not utf8mb3 at T0"; exit 1; }

RAILS='showcase_(haarfabrik|metaldyne|u_zeit)_user'     # persistent-pool users only; uzeit_de (PHP) excluded
echo "$RAILS" > "$W/rails-re.txt"
kubectl -n databases exec mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" --protocol=socket -N -e "SELECT DISTINCT user FROM information_schema.processlist WHERE user LIKE '"'"'showcase%'"'"';"' \
  2>/dev/null | grep -E "^($RAILS)\$" | LC_ALL=C sort > "$W/tenants-T0.txt"
test "$(wc -l < "$W/tenants-T0.txt" | tr -d ' ')" = 3 || { echo "STOP: expected the 3 Rails pool users connected at T0"; cat "$W/tenants-T0.txt"; exit 1; }

kubectl -n my-software-showcase get pods -o 'custom-columns=N:.metadata.labels.app\.kubernetes\.io/name,R:.status.containerStatuses[0].restartCount' --no-headers \
  | LC_ALL=C sort > "$W/restarts-T0.txt"
test "$(wc -l < "$W/restarts-T0.txt" | tr -d ' ')" = 4 || { echo "STOP: not 4 showcase pods (label column) — fix the label key before relying on §4.3"; cat "$W/restarts-T0.txt"; exit 1; }
kubectl -n databases get pod mariadb-0 -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}' > "$W/imageid-T0.txt"
```

Restricting the processlist baseline to the 3 Rails pool users is the
F-9ab5f80f / maintenance-windows.md §7 rule. The 27.3.0 baseline mixed in
per-request PHP users, which made its gate able to fail spuriously.

**2.4 backup_gate (a): logical dump, fail-closed**

```bash
cat > "$W/dump.sh" <<'EOF'
#!/bin/bash
set -euo pipefail
W="$1"; D="$W/mariadb-all-pre-13.1.sql"
kubectl -n databases exec mariadb-0 -c mariadb -- sh -c \
  'mariadb-dump -uroot -p"$MARIADB_ROOT_PASSWORD" --protocol=socket --default-character-set=utf8mb4 --all-databases --single-transaction --routines --triggers --events --flush-privileges' \
  > "$D" 2> "$W/dump.err"
chmod 600 "$D"
tail -1 "$D" | grep -q '^-- Dump completed' || { echo "FAIL: no Dump completed trailer"; exit 1; }
N=$(grep -c '^CREATE DATABASE' "$D"); [ "$N" -ge 9 ] || { echo "FAIL: only $N CREATE DATABASE (measured 9 on 2026-10-05)"; exit 1; }
grep -q '^/\*! FLUSH PRIVILEGES \*/;$' "$D" || { echo "FAIL: no FLUSH PRIVILEGES"; exit 1; }
[ "$(wc -c < "$D")" -ge 1000000 ] || { echo "FAIL: dump < 1 MB (measured 3.17 MB on 2026-10-05)"; exit 1; }
if grep -iv 'password on the command line' "$W/dump.err" | grep -q .; then echo "FAIL: dump stderr:"; cat "$W/dump.err"; exit 1; fi
echo "DUMP_OK $D $(wc -c < "$D") bytes, $N databases"
EOF
chmod 700 "$W/dump.sh"; "$W/dump.sh" "$W" || { echo "STOP: backup_gate (a) failed — do not proceed"; exit 1; }
```

Encoding note: there are no utf8mb4 tables, so the SOP's 4-byte-loss trap
cannot bite. `utf8mb4` on the connection is a superset of latin1 and utf8mb3,
and is kept per the SOP. The dump holds `mysql.global_priv` hashes, so it is
kept `0600` in a `0700` dir, never committed, and deleted in §5.4.

**2.5 restore_proof: the dump restores on the ROLLBACK binary**

A scratch pod on the 13.0.1 digest with an emptyDir datadir. The root password
comes from the same Secret (`secretKeyRef`), so it never touches the Mac
command line and stays valid after the dump's `mysql.global_priv` is loaded.

```bash
cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: mariadb-restoretest
  namespace: databases
  labels: {app.kubernetes.io/name: mariadb-restoretest}
spec:
  restartPolicy: Never
  securityContext: {fsGroup: 1001, runAsUser: 1001, runAsGroup: 1001, runAsNonRoot: true, seccompProfile: {type: RuntimeDefault}}
  containers:
    - name: mariadb
      image: registry-1.docker.io/bitnami/mariadb@sha256:47bdb03b349e22c62443fa91d95b3f10366aa48ce9e4419990c99b7c23400fa9
      env:
        - name: MARIADB_ROOT_PASSWORD
          valueFrom: {secretKeyRef: {name: mariadb, key: mariadb-root-password}}
      securityContext: {allowPrivilegeEscalation: false, capabilities: {drop: [ALL]}}
      resources: {requests: {cpu: 100m, memory: 256Mi}, limits: {memory: 1Gi}}
      volumeMounts: [{name: data, mountPath: /bitnami/mariadb}]
  volumes: [{name: data, emptyDir: {}}]
EOF
for i in $(seq 1 36); do
  kubectl -n databases exec mariadb-restoretest -- sh -c 'mariadb-admin -uroot -p"$MARIADB_ROOT_PASSWORD" --protocol=socket ping' 2>/dev/null | grep -q alive && break; sleep 5
done
kubectl -n databases exec -i mariadb-restoretest -- sh -c \
  'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" --protocol=socket --default-character-set=utf8mb4' \
  < "$W/mariadb-all-pre-13.1.sql" 2> "$W/restoretest.err"; echo "restore rc=$?"
kubectl -n databases exec -i mariadb-restoretest -- sh -s < "$W/counts.sh" > "$W/counts-restoretest.tsv" 2>/dev/null
U=$(kubectl -n databases exec mariadb-restoretest -- sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" --protocol=socket -N -e "SELECT COUNT(*) FROM mysql.global_priv WHERE User LIKE '"'"'showcase%'"'"'"' 2>/dev/null)
echo "restored showcase users: $U"      # measured 4 on the live server 2026-10-05
if [ "$(wc -l < "$W/counts-restoretest.tsv")" -ge 212 ] && diff -q "$W/counts-T0.tsv" "$W/counts-restoretest.tsv" >/dev/null && [ "$U" = 4 ]; then
  echo RESTORE_PROOF_PASS
else
  echo "RESTORE_PROOF_FAIL"; wc -l "$W/counts-restoretest.tsv"; diff "$W/counts-T0.tsv" "$W/counts-restoretest.tsv" | head; cat "$W/restoretest.err"
fi
kubectl -n databases delete pod mariadb-restoretest --wait=true
```

**PASS: `RESTORE_PROOF_PASS`.** This proves the dump reloads into a clean
13.0.1 server with byte-equal per-table counts for all 212 tables and the 4
`showcase_*` accounts. Failure
looks like `RESTORE_PROOF_FAIL` with a short file (for example the pod never
answered `ping`, so 0 lines), or a non-empty diff (for example a tenant schema
missing from the dump). Tenant writes between §2.3 and §2.4 can produce a tiny
diff. If you see one, retake §2.3 counts immediately before §2.4 and re-run.
An unexplained diff is a **STOP**. Do not run §3 without this PASS.

**2.6 backup_gate (b): Longhorn snapshot of the live volume (primary rollback artifact)**

```bash
cat <<'EOF' | kubectl apply -f -
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata:
  name: mariadb-data-pre-13-1
  namespace: databases
spec:
  volumeSnapshotClassName: longhorn-snapshot
  source:
    persistentVolumeClaimName: mariadb-data-5g
EOF
kubectl wait --for=jsonpath='{.status.readyToUse}'=true volumesnapshot/mariadb-data-pre-13-1 -n databases --timeout=300s \
  || { echo "STOP: snapshot not ready"; exit 1; }
VSC=$(kubectl get volumesnapshot mariadb-data-pre-13-1 -n databases -o jsonpath='{.status.boundVolumeSnapshotContentName}')
kubectl get volumesnapshotcontent "$VSC" -o jsonpath='{.status.snapshotHandle}{"\n"}' | tee "$W/snaphandle.txt"   # snap://mariadb-data-5g/snapshot-<uuid>
grep -q '^snap://mariadb-data-5g/' "$W/snaphandle.txt" || { echo "STOP: no snapshot handle recorded"; exit 1; }
```

This snapshot is crash-consistent: it is taken with the server running.
InnoDB and Aria recover from that on start. The §2.4 dump is the
transactionally consistent second layer.

**2.7 Nightly Longhorn backup fresh (third layer)**

```bash
kubectl -n storage get backups.longhorn.io -l backup-volume=mariadb-data-5g \
  --sort-by=.status.backupCreatedAt -o custom-columns='N:.metadata.name,S:.status.state,AT:.status.backupCreatedAt' | tail -1
```

PASS: `Completed` and created at ~03:0x today (`daily-backup-all-volumes`).
Trust the Backup CR, not `lastBackupAt` (`docs/sops/backup.md`).

## 3. Steps

1. **Edit** (dry-tested on a scratch copy of the live file with macOS BSD
   sed + system perl, 2026-10-05; the `old_mode` line is inserted by perl,
   which COPIES the indentation of the `init_connect` line from the file, so
   the result does not depend on how this code block is indented when
   pasted. The earlier `sed a\` form inserted 11 spaces, found in review):

   ```bash
   F=kubernetes/apps/databases/mariadb/app/helmrelease.yaml
   sed -i '' \
    -e 's/^\([[:space:]]*version:[[:space:]]*\)27\.3\.0$/\128.1.1/' \
    -e 's/sha256:47bdb03b349e22c62443fa91d95b3f10366aa48ce9e4419990c99b7c23400fa9/sha256:354e5aec20455bce931a05fa791c51e4a45879015bee09591295c76fe88c037e/' \
    -e 's/This digest is MariaDB 13\.0\.1 (built 2026-08-14)\./This digest is MariaDB 13.1.1 (built 2026-09-30)./' \
    "$F"
   perl -pi -e 's/^([ ]*)init_connect="SET NAMES utf8"\n\z/$&$1old_mode=UTF8_IS_UTF8MB3\n/' "$F"
   sed -i '' '/^  upgrade:$/,/^[[:space:]]*retries:/ s/^\([[:space:]]*retries:[[:space:]]*\)3$/\10/' "$F"
   git diff "$F"
   grep -c '^        old_mode=UTF8_IS_UTF8MB3$' "$F"     # must print 1 (exactly 8 spaces); 0 = not inserted / wrong indent
   ```

   Expected diff: exactly these five changes (`old_mode` indented 8 spaces,
   same as `init_connect`):
   ```
   -      version: 27.3.0                         +      version: 28.1.1
   -      retries: 3        (line 24, upgrade:)   +      retries: 0
   -    # pinned BY DIGEST. This digest is MariaDB 13.0.1 (built 2026-08-14).
   +    # pinned BY DIGEST. This digest is MariaDB 13.1.1 (built 2026-09-30).
   -      digest: "sha256:47bdb03b…400fa9"        +      digest: "sha256:354e5aec…037e"
                                                  +        old_mode=UTF8_IS_UTF8MB3
   ```
   Check that the install block's `retries: 3` (line 19) is **unchanged**.
   `retries: 0` on upgrade is deliberate. With 3, a failed upgrade makes
   helm-controller **roll back by itself to 27.3.0**, starting the 13.0.1
   binary on a datadir the 13.1 binary already touched. That is the exact
   downgrade the SOP forbids, and it would happen unattended and silently.
   Step 9 restores 3. Then validate the render:
   `.venv/bin/python3 -c "import yaml;d=yaml.safe_load(open('$F'));print(d['spec']['upgrade'], [l for l in d['spec']['values']['primary']['configuration'].splitlines() if 'old_mode' in l])"`
   prints `{'cleanupOnFail': True, 'remediation': {'retries': 0}} ['old_mode=UTF8_IS_UTF8MB3']`.

2. **T1 count snapshot** just before pushing (measures natural tenant churn):
   `kubectl -n databases exec -i mariadb-0 -c mariadb -- sh -s < "$W/counts.sh" > "$W/counts-T1.tsv" 2>/dev/null; diff "$W/counts-T0.tsv" "$W/counts-T1.tsv"`

3. **Commit + push** (shared worktree; no `SWEEP_PG_DSN` sourced in this shell):

   ```bash
   git commit --only kubernetes/apps/databases/mariadb/app/helmrelease.yaml \
     -m "feat(mariadb): chart 27.3.0 -> 28.1.1 + digest re-pin to MariaDB 13.1.1, old_mode=UTF8_IS_UTF8MB3 (plan mariadb-28.1.1)"
   git log -1 --format=%s        # must be YOUR subject; amend before push if not
   git show --stat HEAD          # exactly one file
   git push
   echo "$(git rev-parse HEAD)" > "$W/bump-sha.txt"
   ```

4. **Reconcile Kustomization THEN HelmRelease** (mariadb SOP step 4: a
   HelmRelease reconciled first upgrades with stale values while reporting
   Ready). Webhook first. If the HR hasn't picked up 28.1.1 within 5 min:
   `flux reconcile ks -n databases mariadb && flux reconcile hr -n databases mariadb`.

5. **Watch the roll**: `kubectl -n databases get pod mariadb-0 -w`. Expect
   Terminating → Init → Running 1/1 within ~3 min (new image pull). Don't
   delete the pod by hand. If it CrashLoops, go straight to §5.2. Do **not**
   revert git first.

6. **Confirm the new binary is the one running** (rollout status can
   green-light the old generation):
   ```bash
   kubectl -n databases get pod mariadb-0 -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'
   # must contain sha256:354e5aec…037e ; the T0 value (47bdb03b…) = the roll did not happen
   ```

7. **Run mariadb-upgrade by hand: MANDATORY (§1.4)**, over the socket,
   without TLS:
   ```bash
   kubectl -n databases exec mariadb-0 -c mariadb -- sh -c \
     'mariadb-upgrade --protocol=socket --skip-ssl -uroot -p"$MARIADB_ROOT_PASSWORD"' 2>&1 | tee "$W/upgrade.log"
   grep -ciE 'phase [0-9]+/[0-9]+' "$W/upgrade.log"          # expect all phases listed (8 on 13.0; count whatever 13.1 prints)
   grep -iE 'error|gone away|reset by peer' "$W/upgrade.log" && echo "UPGRADE_ERRORS (see SOP Troubleshooting)" || echo UPGRADE_CLEAN
   kubectl -n databases exec mariadb-0 -c mariadb -- cat /bitnami/mariadb/data/mariadb_upgrade_info; echo
   ```
   PASS: `UPGRADE_CLEAN` and the marker reads `13.1.1-MariaDB`. If the run
   stops part-way, re-run it once. The SOP explains why: transport failures
   move around, and a bad statement fails in the same place every time. A
   second failure means §5.2.

8. **Verify (§4).** All gates must PASS before step 9.

9. **Restore upgrade remediation** (separate commit, only after §4 is green):
   ```bash
   F=kubernetes/apps/databases/mariadb/app/helmrelease.yaml
   sed -i '' '/^  upgrade:$/,/^[[:space:]]*retries:/ s/^\([[:space:]]*retries:[[:space:]]*\)0$/\13/' "$F"
   git diff "$F"                     # exactly: -      retries: 0  /  +      retries: 3
   git commit --only "$F" -m "chore(mariadb): restore upgrade remediation retries after 13.1.1 (plan mariadb-28.1.1)"
   git log -1 --format=%s; git show --stat HEAD; git push
   ```
   This re-renders nothing in the pod template, so there is no second roll.
   Check `startTime` is unchanged afterwards.

## 4. Verification

**4.1 Release + binary (floor)**

```bash
kubectl get hr -n databases mariadb -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion} {.status.history[0].appVersion}{"\n"}'
# PASS: True 28.1.1 13.1.1     FAIL: False / 27.3.0 / anything else
kubectl -n databases get pod mariadb-0 -o jsonpath='{.status.startTime} {.status.containerStatuses[0].restartCount}{"\n"}'
# PASS: startTime after the push, restartCount 0
```

**4.2 CONTENTS: engine converted, charset semantics preserved, data intact**

```bash
kubectl -n databases exec mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" --protocol=socket -N -e "SELECT VERSION()" 2>/dev/null; cat /bitnami/mariadb/data/mariadb_upgrade_info; echo'
# PASS: both lines 13.1.1-MariaDB.  FAIL shape (the 12->13 incident): VERSION 13.1.1 + marker 13.0.1 => §3.7 not done
kubectl -n databases exec -i mariadb-0 -c mariadb -- sh -s < "$W/engine.sh" > "$W/engine-T2.txt"
diff "$W/engine-T0.txt" "$W/engine-T2.txt" && echo ENGINE_SAME
```

CONTENTS ASSERTION (charset): `engine-T2.txt` is **identical** to T0. That
means the same 6 users at the same hosts, 12 schemata,
`NO_ENGINE_SUBSTITUTION / SET NAMES utf8 / utf8mb3 / utf8mb3_general_ci`,
**`CONVERT('x' USING utf8)` → `utf8mb3`**, and the same table-collation
histogram. This gate can fail, and here is how. Without `old_mode` (line
missing, mis-indented into `[client]`, or the ConfigMap not rendered), 13.1
prints `utf8mb4` and `utf8mb4_general_ci` in place of the mb3 values. That is
upstream's documented new default (§1.3). `ENGINE_SAME` absent means STOP: the
tenants' charset contract changed. Fix the config forward (the data is not
affected) or go to §5.2. A `sys`-schema difference cannot appear: `engine.sh`
does not read `sys`.

```bash
mariadb_mariadbcheck() { kubectl -n databases exec mariadb-0 -c mariadb -- sh -c \
  'mariadb-check --protocol=socket -uroot -p"$MARIADB_ROOT_PASSWORD" --all-databases 2>&1; echo "RC=$?"'; }
mariadb_mariadbcheck > "$W/check.txt"
grep -q '^RC=0$' "$W/check.txt" && ! grep -viE '[[:space:]]OK$|^RC=0$|^note|^status' "$W/check.txt" | grep -q . \
  && echo CHECK_OK || { echo CHECK_FAIL; grep -viE '[[:space:]]OK$' "$W/check.txt" | head -20; }
```
PASS: `CHECK_OK`. A failed exec prints no `RC=0`. A table needing upgrade or
repair prints a non-`OK` line. Either way the result is `CHECK_FAIL`.

```bash
kubectl -n databases exec -i mariadb-0 -c mariadb -- sh -s < "$W/counts.sh" > "$W/counts-T2.tsv" 2>/dev/null
test "$(wc -l < "$W/counts-T2.tsv")" -ge 212 || echo "FAIL: count file short/empty"
diff "$W/counts-T1.tsv" "$W/counts-T2.tsv"
```
CONTENTS ASSERTION (data): all 212 user tables hold the same exact `COUNT(*)`
as at T1. PASS: an empty diff, or only tables that also moved T0→T1 (tenant
writes). FAIL: line count < 212, a schema at zero, or an empty file (server not
accepting root over the socket).

**4.3 Tenants reconnected: the property a DB roll can silently break**

Wait 3 min after `mariadb-0` is Ready. Then send each app one request that is
measured to execute SQL, and require `200` (paths measured 2026-09-27,
27.3.0 plan §1.4; all four re-checked `200` live 2026-10-05):

```bash
cat > "$W/poke.sh" <<'EOF'
#!/bin/bash
NS=my-software-showcase; P=18300; RC=0
while read APP KIND PORT PATHQ; do
  P=$((P+1))
  kubectl -n $NS port-forward $KIND/$APP $P:$PORT >/dev/null 2>&1 & PF=$!; sleep 2
  CODE=$(curl -s -o /dev/null -m 15 -H 'X-Forwarded-Proto: https' -w '%{http_code}' "http://127.0.0.1:$P$PATHQ")
  kill $PF 2>/dev/null; wait $PF 2>/dev/null
  echo "$APP $PATHQ $CODE"; [ "$CODE" = 200 ] || RC=1
done <<'LIST'
haarfabrik svc 3000 /health/readiness
metaldyne svc 3000 /health/readiness
u-zeit svc 3000 /login
uzeit-de svc 80 /health.php
LIST
exit $RC
EOF
chmod 700 "$W/poke.sh"; "$W/poke.sh" && echo POKE_PASS || echo "POKE_FAIL (non-200 listed above)"

RAILS=$(cat "$W/rails-re.txt")
kubectl -n databases exec mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" --protocol=socket -N -e "SELECT DISTINCT user FROM information_schema.processlist WHERE user LIKE '"'"'showcase%'"'"';"' \
  2>/dev/null | grep -E "^($RAILS)\$" | LC_ALL=C sort > "$W/tenants-T2.txt"
LC_ALL=C comm -23 "$W/tenants-T0.txt" "$W/tenants-T2.txt" > "$W/tenants-missing.txt"
if [ -s "$W/tenants-T2.txt" ] && [ ! -s "$W/tenants-missing.txt" ]; then echo "TENANTS_PASS $(wc -l < "$W/tenants-T2.txt")"; else echo "TENANTS_FAIL missing:"; cat "$W/tenants-missing.txt"; fi
```

PASS requires `POKE_PASS` **and** `TENANTS_PASS 3`. Both the baseline and the
check are restricted to the 3 Rails pool users (F-9ab5f80f), so a PHP app with no
open connection at that instant cannot fail the gate, and a Rails app that
never reconnected cannot pass it. An empty `tenants-T2.txt` also fails. On
FAIL: `kubectl -n my-software-showcase rollout restart deploy/<app>` once,
then re-run both. If it is still failing, the cause is the engine, so go to
§5.2.

**Restart delta (F-9ab5f80f bound)**

```bash
kubectl -n my-software-showcase get pods -o 'custom-columns=N:.metadata.labels.app\.kubernetes\.io/name,R:.status.containerStatuses[0].restartCount' --no-headers \
  | LC_ALL=C sort > "$W/restarts-T2.txt"
LC_ALL=C join "$W/restarts-T0.txt" "$W/restarts-T2.txt" | awk '{d=$3-$2; print $1, d; if (d>=2 || d<0) bad=1} END{exit bad}' \
  && echo RESTARTS_PASS || echo "RESTARTS_FAIL (delta >=2 = restart loop; negative = pod replaced, inspect)"
test "$(LC_ALL=C join "$W/restarts-T0.txt" "$W/restarts-T2.txt" | wc -l | tr -d ' ')" = 4 || echo "RESTARTS_FAIL: not all 4 tenants joined"
```

PASS: every tenant's restart delta is 0 or 1, and all 4 joined. Expected is
**0** everywhere: Rails liveness is `tcpSocket` since f515915c, and uzeit-de
did not restart on the 2026-10-03 bounce. A delta of 1 is still a PASS (SOP
§7: a DB bounce may restart each consumer at most once; on 2026-10-03 five
Rails tenants did, under the old probe), but record it in the run log: a
Rails restart with `tcpSocket` liveness means the f515915c premise no longer
explains the behaviour. A delta ≥2 is a restart
loop: FAIL.

**4.4 phpMyAdmin**

```bash
kubectl -n databases port-forward svc/phpmyadmin 18090:80 >/dev/null 2>&1 & PF=$!; sleep 2
curl -s -m 10 http://127.0.0.1:18090/ | grep -ciE 'phpmyadmin|pma_username' ; kill $PF
```
PASS: count ≥1 (login page rendered). This only proves phpMyAdmin itself is up:
the login page renders without a DB backend, so it cannot fail on a MariaDB
outage (review 2026-10-05). The DB-facing gate is the attended login: log in once and confirm
the 4 `showcase_*_prod` and 2 `ibTime_*` schemas are listed.

**4.5 Instruments**

CONTROL: metric kube_statefulset_status_replicas_ready — `{namespace="databases",statefulset="mariadb"}` must read 1 (T0 = 1); 0 for >5 min after the push = the 13.1 pod never became Ready.
CONTROL: metric kube_pod_status_ready — `sum(kube_pod_status_ready{namespace="my-software-showcase",condition="true"})` must return to 4 (T0 = 4, measured 2026-10-05) within 5 min of `mariadb-0` Ready; a value stuck below 4 names a tenant that did not reconnect.
CONTROL: metric kube_pod_container_status_restarts_total — `round(increase(kube_pod_container_status_restarts_total{namespace="my-software-showcase"}[45m]))` must be ≤ 1 for every series (same bound as the kubectl delta above; ≥ 2 = restart loop ⇒ FAIL). `round()` is required: `increase()` extrapolates, and replaying the 2026-10-03 bounce it read 1.005 for a single restart, which would fail a raw ≤ 1 on the case SOP §7 allows (plan review 2026-10-05).
DIAGNOSTIC (not a gate): `kubectl -n databases logs mariadb-0 -c mariadb | grep -iE 'old_mode|deprecat'` should show the expected UTF8_IS_UTF8MB3 deprecation warning. Its ABSENCE is not a failure (the §4.2 CONVERT gate is the control), but a `[ERROR] unknown variable 'old_mode…'` would be — the pod would not be Ready either.

Then delete the silence and clear the marker (`runbooks/update-marker.sh clear mariadb`). After that, run §3 step 9.

## 5. Rollback

**Forward-only from §3 step 5 onward.** Once the 13.1 binary has opened the
datadir, and certainly after §3.7, the system tables are 13.1-format.
`git revert` **alone** points the 13.0.1 binary at them. That is worse than
doing nothing (SOP Rollback Plan). The upgrade's `retries: 0` keeps Helm from
doing that by itself.

**5.1 Failure before §3 step 3 (premises, dump, restore proof, snapshot):** stop.
Nothing changed. `git checkout -- kubernetes/apps/databases/mariadb/app/helmrelease.yaml`
if step 1 was already done. Leave the VolumeSnapshot for §5.4.

**5.2 Any failure after the push: quiesced Longhorn snapshot revert (primary)**

> STORAGE SAFETY: this is a snapshot **revert on the same volume**. Do not
> delete or recreate `mariadb-data-5g` (PVC or PV). The PV is `Retain`,
> `longhorn-static`, with `volumeHandle mariadb-data-5g` (live 2026-10-04).
> If any step seems to need a PVC delete, run the CLAUDE.md 3-step pre-flight
> and STOP.

Step 1: quiesce. Suspend the Kustomization **and** the HR, both in namespace
`databases`, then scale to 0.
```bash
flux suspend kustomization mariadb -n databases
flux suspend helmrelease   mariadb -n databases
kubectl -n databases scale sts/mariadb --replicas=0
kubectl -n databases wait --for=delete pod/mariadb-0 --timeout=180s
kubectl get volume -n storage mariadb-data-5g -o jsonpath='{.status.state}{"\n"}'    # MUST be: detached
```
Don't proceed while `mariadb-0` exists or the volume is not `detached`.

Step 2: revert the volume (operator at the Longhorn UI). `cat "$W/snaphandle.txt"`
gives `snap://mariadb-data-5g/snapshot-<uuid>`. Cross-check it with
`kubectl get snapshots.longhorn.io -n storage -l longhornvolume=mariadb-data-5g -o custom-columns='NAME:.metadata.name,CREATED:.status.creationTime,USER:.status.userCreated'`.
Then in the Longhorn UI: Volume `mariadb-data-5g` → **Attach** with
**Maintenance mode** → Snapshots → that snapshot → **Revert** → **Detach**.
This is the same procedure as n8n-2.39.8 §5.2 and paperless-db-13.0.2 §5.

Step 3: put the 13.0.1 binary back and resume.
```bash
git revert --no-edit "$(cat "$W/bump-sha.txt")"   # restores 27.3.0, the 13.0.1 digest, no old_mode, retries: 3
git log -1 --format=%s; git show --stat HEAD; git push
flux resume kustomization mariadb -n databases
flux resume helmrelease   mariadb -n databases     # Helm re-renders replicas: 1
```
If §3 step 9 had already landed, revert that commit as well (retries back to
3 is harmless at this point).

Confirm recovery. Each check has a known-bad reading:
- imageID contains `47bdb03b…` (a 13.1 pod shows `354e5aec…`);
- §4.2 version + marker both `13.0.1-MariaDB`. A marker of `13.1.1` means the
  wrong snapshot or the revert did not take. Go to §5.3;
- `diff "$W/engine-T0.txt" <(kubectl -n databases exec -i mariadb-0 -c mariadb -- sh -s < "$W/engine.sh")` is empty;
- the counts diff against `counts-T1.tsv` is empty apart from rows written
  between snapshot and failure, which are lost by design (tenant demo data, a
  window of minutes);
- `POKE_PASS` and `TENANTS_PASS 3`.

**5.3 Floor: logical restore of the §2.4 dump (only if §5.2 fails)**

This dump has already been proven to restore on 13.0.1 (§2.5). With the
volume on the 13.0.1 binary (after a successful snapshot revert whose data is
suspect), load it into the running server:
```bash
kubectl -n databases exec -i mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" --protocol=socket --default-character-set=utf8mb4' \
  < "$W/mariadb-all-pre-13.1.sql"
```
Then re-run the counts diff against `counts-T0.tsv`. If the snapshot itself
cannot be reverted, restore the §2.7 nightly Backup CR per `docs/sops/backup.md`
→ "Restore from Backup". That lands as a **new volume name**, and the PV's
`volumeHandle` is immutable, so rebinding means editing the git-tracked
`pv.yaml`/`pvc.yaml`. That is operator-present only. Never delete the old
PV/PVC (Retain).

**5.4 Cleanup (after 7 clean days):**
`kubectl -n databases delete volumesnapshot mariadb-data-pre-13-1` (class
`deletionPolicy: Delete` removes the Longhorn snapshot it made, not the
volume) and `rm -rf "$W"` (the dump contains password hashes).

## 6. Interference notes

- **Shared DB, one-way.** `mariadb-0` is down for ~2–3 min (new image pull +
  start), and the server runs 13.1 binaries on 13.0 system tables for the
  ~1 min until §3.7 completes. 4 showcase tenants and phpMyAdmin are
  affected. No household service uses this instance.
- **Attended only.** `risk: high` + `rollback_class: backup-restore` →
  human-gated. §5.2 needs an operator at the Longhorn UI. Forward path is 55
  min, and ~90 with rollback, so it does not fit the 70-min sat-attended
  budget with rollback headroom. **sun-attended** (180) is the right slot.
- **conflicts_with** carries every live backup-restore plan (rollback-class
  stacking, same convention as paperless-db-13.0.2) and every plan that
  touches this HR, its chart source, helm-controller, the tenant set, DNS, the
  node or Longhorn. `nocodb-2026.09.1` shares namespace `databases` (different
  engine) and is backup-restore. It is listed for the stacking reason, not
  shared objects.
- **Namespace `databases` is also touched by `redis-fleet-8.10.2` and
  `pgvector-fleet-0.8.7`** (git-revert class, different engines). They share
  no object, Service or PVC with `mariadb`, so they are not in
  `conflicts_with`. The window agent's namespace-overlap check will still flag
  them; serialize rather than run them in parallel, so a §4 failure is
  attributable.
- **Re-plan 2026-10-05.** The 2026-10-04 showcase decommission shrank the
  consumer set from 15 to 4 apps, the tenant baseline from 12 to 3 Rails pool
  users, and the data from 586 to 212 tables. Every gate count in §2–§5 was
  re-measured live, not derived. If a tenant is added or removed before the
  window, the `four-showcase-tenants` premise fails and this plan must be
  re-measured again.
- **paperless-db-13.0.2 is listed for stacking only.** It shares no object
  with this plan. Its own mariadb trap (the 13.1 charset default) does not
  apply to it at 13.0.2, but will apply to its next hop. The same applies to
  `bitnamilegacy-exit-nextcloud-db`.
- **Dual-owned Secret.** `secret/databases/mariadb` is applied by kustomize
  (SOPS, 4 keys) and rendered by the chart. On auth failures in §4, first
  check it still has `mariadb-database mariadb-password mariadb-root-password
  mariadb-user`.
- **Follow-up owed (not in this plan):** `old_mode=UTF8_IS_UTF8MB3` is
  deprecated as of 13.1. Before upstream removes it, the tenants' charset
  contract must be made explicit (`utf8mb3` names, or a deliberate tenant
  migration to utf8mb4). That is an operator decision about the legacy
  tenants. Re-check the flag on every later re-pin.
- **The digest pin freezes patching** (SOP Security Check). No tooling
  surfaces drift on a `digest:`-only block. The next re-pin is again a manual
  plan.
- The legacy `ingress:` values block (F-457e6d05) renders nothing in 28.1.1
  either (no ingress template in the chart). It is untouched here.
- No reboot, no drain, no Longhorn engine change.
