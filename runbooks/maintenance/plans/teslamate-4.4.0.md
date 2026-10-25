---
plan_id: teslamate-4.4.0
component: teslamate                  # HelmRelease home-automation/teslamate (bjw-s app-template 5.3.0), image teslamate/teslamate
pr: 266                               # Renovate "feat(container): update teslamate/teslamate ( 4.3.0 → 4.4.0 )" — CI green 2026-10-25
                                      # (Flate Render Gate, Flux Local Diff helmrelease+kustomization: pass)
kind: image
current: "4.3.0"                      # MEASURED live 2026-10-25: deploy image teslamate/teslamate:4.3.0@sha256:516fc9f0…,
                                      # pod imageID same digest, `bin/teslamate version` -> "teslamate 4.3.0"
target: "4.4.0"                       # coverage reported the floating series tag "4.4"; resolved to the FIXED tag 4.4.0:
                                      # Docker Hub 4.4.0 == 4.4 == latest, index digest sha256:c85b3d44…a5d31 (amd64+arm64 active),
                                      # pushed 2026-10-23T15:11Z; GitHub release v4.4.0 published 2026-10-23T16:09Z,
                                      # prerelease=false. No 4.4.x newer than 4.4.0 exists (only `edge` is newer).
update_type: minor
risk: low                             # two tiny, reversible Ecto migrations on a 620 MB DB (§1.2); no config/env change needed;
                                      # rollback measured transparent for 4.3.0 (§1.3). Single-car logger, no other writer.
est_duration_min: 25                  # 8 pre-checks + pg_dump (~2 min), 2 merge/push, ~4 reconcile+Recreate, 8 verification, 3 buffer
needs_reboot: false
touches:
  namespaces: [home-automation]
  resources:                          # every object verified to EXIST live 2026-10-25 (kubectl get)
    - helmrelease/teslamate           # the only object this plan EDITS (values.controllers.main.containers.main.image.tag)
    - deployment/teslamate            # pod template image changes -> ONE pod roll; strategy Recreate (verified live)
    - deployment/teslamate-postgres   # NOT edited / not restarted; its DB `teslamate` receives the two schema migrations
    - pvc/teslamate-db                # RWO longhorn-static (PV/volume teslamate-db) holding the postgres data dir
    - httproute/teslamate             # unchanged spec; serves 503 for the ~30-60 s Recreate gap
    - service/teslamate
  shared:
    - mosquitto                       # teslamate re-publishes its retained teslamate/cars/1/* topics on mosquitto-internal at start;
                                      # 4.4.0 changes the MQTT payload contract (§1.1) — measured: no HA/discovery consumer
    - grafana                         # monitoring/grafana datasource uid TeslaMate + 11 provisioned dashboards read this DB (§4.5)
    - monitoring                      # §4 reads Prometheus (kube-state-metrics series)
depends_on: []
conflicts_with:                       # every id below exists in runbooks/maintenance/plans/ on 2026-10-25
  - longhorn-1.13.0                     # shares the storage layer teslamate-db rides on; never the same night
  - helm-drift-detection              # adds spec.driftDetection to every HR incl. helmrelease/teslamate (same object)
  - flux-oci-chart-sources            # rewrites the bjw-s chart source block of every app-template HR incl. this one
                                      # (no kube-prometheus-stack or grafana plan is open today; add it here if one appears)
exclusive: false
security_ref: null                    # no security driver (per dispatch; image CVE rows stay on their own DB findings)
capability_change: true               # NOT a same-behaviour bump: upstream changes the MQTT payload CONTRACT ("a value the car
                                      # reports as missing is now published as an empty MQTT topic … before, the last value
                                      # stayed") and stops trusting eight CA intermediates. Measured: nothing in HA consumes
                                      # teslamate/* (no discovery configs, no YAML ref) so no consumer breaks — but a changed
                                      # published API is a capability change by definition, declared truthfully.
rollback_class: git-revert            # MEASURED from upstream code (§1.3): both new migrations are reversible, and 4.3.0 neither
                                      # names the Postgres enum type (Ecto.Enum stores strings) nor cares about the
                                      # import_runs.car_id width -> 4.3.0 boots on the migrated DB. The pg_dump in §2.6 is the
                                      # contingency (§5.B), not the rollback path.
finding_refs: [F-0d5d7631]            # version finding "teslamate: image teslamate/teslamate 4.3.0@sha256:516fc9f0… → 4.4"
review: ready-for-go@2026-10-25   # plan-reviewer 2026-10-25: 0 blocking, premises 6/6
premises:
  - id: live-image-is-4.3.0
    why: >-
      The rollback target and the "migrations not yet applied" baseline both assume the serving
      pod runs the 4.3.0 digest. If something already moved it, re-plan.
    run: kubectl get deploy teslamate -n home-automation -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "teslamate/teslamate:4.3.0@sha256:516fc9f0a14369f541b1a70ff2f65dd9b57c2e01c1f533b6d43b375445404955"
  - id: hr-ready-at-current-generation
    why: "No in-flight upgrade to stack on; git revert must land on a known-good revision."
    run: kubectl get helmrelease teslamate -n home-automation -o jsonpath='{.metadata.generation}={.status.observedGeneration}={.status.conditions[?(@.type=="Ready")].status}'
    expect_matches: '^(\d+)=\1=True$'
  - id: repo-pins-4.3.0-once
    why: "§3.1b's fallback sed assumes exactly one matching tag line in the HR file (run from the repo root)."
    run: "grep -c 'tag: \"4.3.0@sha256:516fc9f0a14369f541b1a70ff2f65dd9b57c2e01c1f533b6d43b375445404955\"' kubernetes/apps/home-automation/teslamate/app/helmrelease.yaml"
    expect_exact: "1"
  - id: strategy-recreate
    why: >-
      Two TeslaMate processes must never run the same migrations / log the same car concurrently.
      Verified Recreate on 2026-10-25 (the pod mounts no RWO PVC itself; postgres does).
    run: kubectl get deploy teslamate -n home-automation -o jsonpath='{.spec.strategy.type}'
    expect_exact: "Recreate"
  - id: postgres-is-18
    why: "Upstream logs a PostgreSQL compatibility check at start; plan measured against postgres:18.6."
    run: kubectl get deploy teslamate-postgres -n home-automation -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "postgres:18.6"
  - id: nightly-backup-exists
    why: >-
      Contingency §5.C restores the newest Completed Longhorn backup of teslamate-db. Existence only —
      FRESHNESS is the §2.5 gate.
    run: kubectl get backups.longhorn.io -n storage -l backup-volume=teslamate-db -o jsonpath='{.items[*].status.state}'
    expect_contains: Completed
status: vetted
window: nightly:2026-11-06   # human-gated (capability_change): needs operator GO; car parked/asleep
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/longhorn.md
  - docs/sops/grafana-image-changes.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-25"
---

# teslamate: image 4.3.0 -> 4.4.0 (two reversible schema migrations; MQTT empty-value contract change)

## 1) Summary & why held

`home-automation/teslamate` is the single-car Tesla logger: bjw-s app-template 5.3.0, one
Deployment (`strategy: Recreate`), image `teslamate/teslamate:4.3.0@sha256:516fc9f0…`, no PVC of
its own. Its database is the sibling HelmRelease `teslamate-postgres` (image `postgres:18.6`,
Service `teslamate-postgres`, data on RWO `longhorn-static` PVC/volume `teslamate-db`, 10 Gi,
2 replicas, DB size 620 MB, nightly Longhorn backup via `storage/daily-backup-all-volumes` @ 23:00 UTC).
Exposed only on `envoy-internal` (HTTPRoute `home-automation/teslamate`, `sectionName: https`).
Publishes to `mosquitto-internal.home-automation` (plain 1883, anonymous). Grafana
(`monitoring/grafana`) reads the same DB through datasource uid `TeslaMate` and provisions 11
dashboards in folder `TeslaMate`. Renovate PR #266 is a one-line tag+digest bump, CI green.
Answers finding `F-0d5d7631`.

**Why held:** coverage reported target `4.4` — a floating series tag with fewer version components
than the pinned `4.3.0`, which the gate refuses to treat as a fixed version. Resolved from primary
sources: Docker Hub `teslamate/teslamate` tags `4.4.0`, `4.4` and `latest` all carry index digest
`sha256:c85b3d447502683ed7bf12fb478e0dae9a985fe975ac22cccb64faeb4c4a5d31` (amd64 + arm64,
pushed 2026-10-23T15:11Z); GitHub release `v4.4.0` (teslamate-org/teslamate) published
2026-10-23T16:09Z, `prerelease: false`. **The fixed target is 4.4.0@sha256:c85b3d44…a5d31** —
exactly what PR #266 pins. A minor bump with schema migrations and a changed MQTT contract is
also not auto-safe on its own merits.

### 1.1 Release notes v4.4.0 — the parts that touch us (quoted)

| Upstream note | Applies to us? | Evidence |
|---|---|---|
| "**Note for MQTT users:** A value the car reports as missing is now published as an empty MQTT topic, e.g. `speed` and `shift_state` once the car is switched off; before, the last value stayed. … A topic the car has not reported since TeslaMate started is no longer cleared … the `odometer` never decreases and is never published empty." | **Contract change, no consumer measured.** HA has no teslamate integration (`core.config_entries`: only `tesla_wall_connector`, `teslafi`), no `/config/**/*.yaml` references `teslamate`, and `mosquitto_sub -t 'homeassistant/+/+/config'` shows 0 teslamate discovery configs (measured 2026-10-25). Declared as `capability_change: true`. | §4.6 |
| "TeslaMate no longer trusts these CAs [eight eMudhra intermediates] … (#5882)" | Tesla API/streaming are not on those CAs; our MQTT is plain TCP. No effect expected; §4.3 proves the Tesla API still authenticates. | log line `Refreshed api tokens` |
| "The Docker image now ships the CA certificates, so time zone updates download again (#5808)" | **Yes — a fix we can measure.** 4.3.0 logs `Tzdata cannot verify TLS certificates on this Erlang/OTP version.` ~5 s after every start (measured: pod start 2026-10-22T20:49:44, and daily at 02:49). | §4.2 gate |
| "we use the latest Grafana (13.2.4)" | **No.** That is the bundled `teslamate/grafana` image, which we do not run; our Grafana is `monitoring/grafana`. | grafana HR |
| Dashboards: Visited / Temperatures / Charging Stats changes | **Not coupled to this bump.** Our Grafana provisions TeslaMate dashboards from `raw.githubusercontent.com/teslamate-org/teslamate/master/grafana/dashboards/*.json` — unpinned `master`, fetched at Grafana pod start, so they already track post-4.4 master regardless of the app version. | `kubernetes/apps/monitoring/grafana/app/helmrelease.yaml` lines ~327-360 |
| `fix(db): align import_runs.car_id type with cars.id (smallint) (#5847)`; `refactor(db): rename the range enum to preferred_range (#5860)` | **Yes — the two schema migrations, §1.2.** | upstream source |

### 1.2 Database migrations — measured from upstream code, not assumed

Shallow clone of tag `v4.4.0`, `elixir/priv/repo/migrations/`: the newest applied version live is
`20260808090000` (`select version from schema_migrations order by version desc` → `20260808090000`,
105 rows). 4.4.0 adds exactly two:

- `20261009120000_align_import_runs_car_id_type.exs` — `modify(:car_id, :smallint, from: :bigint)`
  on `import_runs`. Live: `import_runs` has **0 rows**, column is `bigint` → instant, cannot lose
  data (FK to `cars.id` which is already smallint; Postgres raises rather than truncates).
- `20261014120000_rename_range_enum_to_preferred_range.exs` —
  `execute("ALTER TYPE range RENAME TO preferred_range", "ALTER TYPE preferred_range RENAME TO range")`.
  Catalog-only rename. Live: `pg_type` has `range`, no `preferred_range`.

Migrations run automatically at container start (`/entrypoint.sh`:
`bin/teslamate eval "TeslaMate.Release.wait_for_database_and_migrate()"`), as `DATABASE_USER`,
which is also `POSTGRES_USER` (the DB owner) → no privilege problem for `ALTER TYPE`.

### 1.3 Rollback compatibility (why `rollback_class: git-revert`)

- Both migrations have a `down` path, but a downgrade does not need it: 4.3.0 declares the column
  as `field :preferred_range, Ecto.Enum, values: [:ideal, :rated]` (`elixir/lib/teslamate/settings/global_settings.ex`
  @v4.3.0) — Ecto.Enum sends strings, never the type name. `grep -rnE '::range|TYPE range'` over
  v4.3.0 `elixir/lib` and v4.4.0 `grafana/dashboards` → 0 hits. A `smallint` `import_runs.car_id`
  is wire-compatible with 4.3.0's integer field.
- Ecto ignores applied migration versions it does not embed, so 4.3.0 starts with
  "Migrations already up".
- ⇒ reverting the tag is a complete rollback; the §2.6 dump only matters if the DB itself is damaged.

## 2) Pre-checks

Run from `/Users/mu/code/cberg-home-nextgen` in zsh. Any FAIL → stop, do not merge.

2.1 Premises (all six must pass):
```bash
.venv/bin/python3 runbooks/plan-premises.py teslamate-4.4.0
```

2.2 Flux and the two HRs healthy, PR still open and green:
```bash
flux get helmreleases -n home-automation | grep -E 'NAME|teslamate'      # both teslamate + teslamate-postgres Ready=True
gh pr view 266 --json state,mergeable,headRefOid --jq '.state+" "+.mergeable'   # PASS: "OPEN MERGEABLE"
gh pr checks 266                                                          # PASS: every line "pass"
gh pr diff 266 | grep -c '^+.*4.4.0@sha256:c85b3d447502683ed7bf12fb478e0dae9a985fe975ac22cccb64faeb4c4a5d31'  # PASS: 1
```
FAIL shape: a re-based PR pointing at a different digest prints 0 on the last line.

2.3 Car not mid-drive/mid-charge (a Recreate during a drive splits it into two drives):
```bash
P=$(kubectl -n home-automation get pod -l app.kubernetes.io/name=mosquitto -o name | head -1)
kubectl -n home-automation exec $P -c app -- timeout 4 mosquitto_sub -h localhost -t 'teslamate/cars/1/state' -v -C 1
```
PASS: `asleep`, `online`, `suspended` or `offline`. If `driving` or `charging` → wait or defer
(a split charge is cosmetic; operator may accept it — interruption is fine, data loss is not).

2.4 Baselines (record the numbers in the window log; §4 diffs against them):
```bash
kubectl -n home-automation exec deploy/teslamate-postgres -- sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "
select '"'"'mig_max='"'"'||max(version) from schema_migrations;
select '"'"'mig_n='"'"'||count(*) from schema_migrations;
select '"'"'positions='"'"'||count(*) from positions;
select '"'"'drives='"'"'||count(*) from drives;
select '"'"'charging_processes='"'"'||count(*) from charging_processes;
select '"'"'cars='"'"'||count(*) from cars;
select '"'"'type='"'"'||string_agg(typname,'"'"','"'"') from pg_type where typname in ('"'"'range'"'"','"'"'preferred_range'"'"');
select '"'"'car_id_type='"'"'||data_type from information_schema.columns where table_name='"'"'import_runs'"'"' and column_name='"'"'car_id'"'"';"'
```
Measured 2026-10-25: `mig_max=20260808090000`, `mig_n=105`, `positions=4551078`, `drives=1741`,
`charging_processes=373`, `type=range`, `car_id_type=bigint`.

2.5 Longhorn backup fresh (< 26 h):
```bash
kubectl get volume teslamate-db -n storage -o jsonpath='{.status.lastBackupAt} {.status.robustness}{"\n"}'
kubectl get backups.longhorn.io -n storage -l backup-volume=teslamate-db \
  -o custom-columns=N:.metadata.name,S:.status.state,T:.status.backupCreatedAt --no-headers | sort -k3 | tail -1
```
PASS: newest `Completed` backup created within the last 26 h and robustness `healthy`
(measured 2026-10-25: `backup-89df5273c08e404e` Completed 2026-10-24T23:07:48Z, healthy).

2.6 Logical dump to the Mac (the §5.B contingency artifact):
```bash
mkdir -p /Users/mu/backups/teslamate
TS=$(date +%Y%m%d_%H%M%S); DUMP=/Users/mu/backups/teslamate/teslamate-pre-4.4.0-$TS.dump
kubectl -n home-automation exec deploy/teslamate-postgres -- sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$DUMP"
ls -l "$DUMP"
pg_restore -l "$DUMP" | grep -c 'TABLE DATA public positions'   # PASS: 1   (needs a local pg_restore; else run the list in-pod: see below)
echo "$DUMP"
```
If no local `pg_restore`: `kubectl -n home-automation exec -i deploy/teslamate-postgres -- pg_restore -l < "$DUMP" | grep -c 'TABLE DATA public positions'`.
FAIL shape: an auth or OOM failure leaves a 0-byte or few-KB file and the grep prints 0. Expect
roughly 100-300 MB. Mac free space measured 27 GiB.

## 3) Steps

3.1 Merge the Renovate PR (preferred):
```bash
gh pr merge 266 --squash --delete-branch
git pull --ff-only
grep -n 'tag: "4.4.0@sha256:c85b3d447502683ed7bf12fb478e0dae9a985fe975ac22cccb64faeb4c4a5d31"' \
  kubernetes/apps/home-automation/teslamate/app/helmrelease.yaml          # PASS: one line (36)
```

3.1b Fallback only if PR #266 was closed/superseded (dry-tested on a scratch copy with BSD sed 2026-10-25):
```bash
sed -i '' 's|tag: "4.3.0@sha256:516fc9f0a14369f541b1a70ff2f65dd9b57c2e01c1f533b6d43b375445404955"|tag: "4.4.0@sha256:c85b3d447502683ed7bf12fb478e0dae9a985fe975ac22cccb64faeb4c4a5d31"|' \
  kubernetes/apps/home-automation/teslamate/app/helmrelease.yaml
git diff --stat   # exactly 1 file, 1 insertion, 1 deletion
git commit --only kubernetes/apps/home-automation/teslamate/app/helmrelease.yaml \
  -m "feat(teslamate): 4.3.0 -> 4.4.0 (plan teslamate-4.4.0)"
git log -1 --format=%s   # must be YOUR subject; amend before push if not (shared worktree)
git show --stat HEAD     # only the helmrelease file
git push
```
Dry-test diff:
```
36c36
<               tag: "4.3.0@sha256:516fc9f0a14369f541b1a70ff2f65dd9b57c2e01c1f533b6d43b375445404955"
---
>               tag: "4.4.0@sha256:c85b3d447502683ed7bf12fb478e0dae9a985fe975ac22cccb64faeb4c4a5d31"
```

3.2 Let the push webhook reconcile (no manual `flux reconcile` unless nothing moves within 10 min,
per `docs/sops/application-update.md`). Watch:
```bash
kubectl -n home-automation get pods -l app.kubernetes.io/name=teslamate -w   # old Terminating -> new Running 1/1
```

## 4) Verification

4.1 Live pod runs the new digest (not just a green rollout — `feedback_rollout_status_old_generation`):
```bash
kubectl -n home-automation get pod -l app.kubernetes.io/name=teslamate -o jsonpath='{range .items[*]}{.status.containerStatuses[0].imageID}{"\n"}{end}'
kubectl -n home-automation exec deploy/teslamate -- bin/teslamate version
```
PASS: exactly one pod, imageID ends `@sha256:c85b3d447502683ed7bf12fb478e0dae9a985fe975ac22cccb64faeb4c4a5d31`;
version prints `teslamate 4.4.0`. FAIL shape: today it prints `teslamate 4.3.0` / `516fc9f0…`.

4.2 Startup log: migrations ran, upstream CA fix is real, Tesla + MQTT connected (case-insensitive):
```bash
kubectl -n home-automation logs deploy/teslamate --since=10m > /tmp/tm-start.log
grep -ci 'Version: 4.4.0' /tmp/tm-start.log                          # PASS: >=1
grep -ci 'Tzdata cannot verify TLS' /tmp/tm-start.log                # PASS: 0   (4.3.0 baseline: 1 at every start, measured)
grep -ci 'Migrations already up' /tmp/tm-start.log                   # PASS: 0   (there WERE migrations to run)
grep -ci 'MQTT connection has been established' /tmp/tm-start.log    # PASS: >=1
grep -ci 'Refreshed api tokens' /tmp/tm-start.log                    # PASS: >=1 (Tesla auth still works after the CA change)
grep -ciE '\[error\]|\*\* \(' /tmp/tm-start.log                       # PASS: 0
```
Wait until the pod is ≥60 s old before reading (the Tzdata line arrived ~5 s after start on 4.3.0).

4.3 CONTENTS ASSERTION: schema migrated AND data intact — measured by the §2.4 query, compared to the §2.4 baseline.
PASS, all of: `mig_max=20261014120000`; `mig_n=107` (baseline +2); `type=preferred_range` (no `range`);
`car_id_type=smallint`; `drives`, `charging_processes`, `cars` **equal** to baseline (or +1 if a
drive/charge closed meanwhile) and `positions` **≥** baseline. FAIL shapes: an un-run migration
shows `type=range` / `bigint`; a wiped or wrong DB shows positions far below 4,551,078 — a
structurally healthy app on an empty DB would still pass 4.1/4.2, this is the gate that would not.

4.4 Web UI serves the car through the route path:
```bash
kubectl -n home-automation port-forward svc/teslamate 14000:4000 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s -o /tmp/tm.html -w '%{http_code}\n' http://localhost:14000/      # PASS: 200
grep -c 'Tessy' /tmp/tm.html                                              # PASS: >=1 (car name rendered from DB)
kill $PF 2>/dev/null
```
(The car name appears in the startup log as `Starting logger for 'Tessy'`; a page with no car prints 0.)

4.5 Grafana still reads the migrated DB (shared consumer; `docs/sops/grafana-image-changes.md`):
```bash
U=$(kubectl -n monitoring get secret grafana-admin-secret -o jsonpath='{.data.admin-user}' | base64 -d)
PW=$(kubectl -n monitoring get secret grafana-admin-secret -o jsonpath='{.data.admin-password}' | base64 -d)
kubectl -n monitoring port-forward svc/grafana 13000:80 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s -u "$U:$PW" http://localhost:13000/api/datasources/uid/TeslaMate/health            # PASS: "status":"OK"
curl -s -u "$U:$PW" -H 'Content-Type: application/json' http://localhost:13000/api/ds/query \
  -d '{"queries":[{"refId":"A","datasource":{"uid":"TeslaMate"},"rawSql":"select preferred_range::text as p, (select count(*) from drives) as n from settings limit 1","format":"table"}],"from":"now-1h","to":"now"}'
                                                                                            # PASS: values [["ideal"|"rated"],[>=1741]]
kill $PF 2>/dev/null
```
FAIL shape: a broken enum rename makes the second query return an `error` key instead of frames;
a datasource auth break prints `"status":"ERROR"`. (Measured on 4.3.0: health OK, `count(*) from drives` = 1741.)

4.6 MQTT re-published and the contract change is observed, not assumed:
```bash
P=$(kubectl -n home-automation get pod -l app.kubernetes.io/name=mosquitto -o name | head -1)
kubectl -n home-automation exec $P -c app -- timeout 4 mosquitto_sub -h localhost -t 'teslamate/cars/1/#' -v > /tmp/tm-mqtt.txt
grep -c '^teslamate/cars/1/odometer [0-9]' /tmp/tm-mqtt.txt      # PASS: 1 (odometer never published empty, per notes)
grep -c '^teslamate/cars/1/state ' /tmp/tm-mqtt.txt              # PASS: 1
kubectl -n home-automation exec $P -c app -- timeout 4 mosquitto_sub -h localhost -t 'homeassistant/+/+/config' -v | grep -ci teslamate   # PASS: 0 (still no HA consumer)
```
If the last line is non-zero, someone enabled HA discovery since 2026-10-25 → report it: sensors
may go `unknown` while the car sleeps (expected per upstream, not a regression).

4.7 Prometheus (kube-state-metrics), 10 min after the roll:
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s -G http://localhost:19090/api/v1/query --data-urlencode 'query=kube_deployment_status_replicas_available{namespace="home-automation",deployment="teslamate"}'
curl -s -G http://localhost:19090/api/v1/query --data-urlencode 'query=increase(kube_pod_container_status_restarts_total{namespace="home-automation",pod=~"teslamate-.*",container="main"}[10m])'
kill $PF 2>/dev/null
```
CONTROL: metric kube_deployment_status_replicas_available — exactly one series, value `1` (an empty result is a FAIL, not a pass: measured 1 series today).
CONTROL: metric kube_pod_container_status_restarts_total — increase over 10 m on the new pod `0` (a migration crash-loop shows ≥1).

## 5) Rollback

**Trigger:** any §4 FAIL, crash-loop, or the operator's call.

5.A Image rollback (the rollback path; DB stays migrated — measured compatible, §1.3):
```bash
git revert --no-edit <merge-sha-of-PR-266>      # or the §3.1b commit
git log -1 --format=%s                          # confirm it is YOUR revert
git show --stat HEAD                            # only teslamate/app/helmrelease.yaml
git push
```
Confirm: §4.1 shows imageID `@sha256:516fc9f0…` and `teslamate 4.3.0`; logs show
`Migrations already up` and `Version: 4.3.0`; §4.3 counts still match baseline; §4.4 200 + car name.
Do NOT run the down migrations — 4.3.0 does not need them, and a later re-upgrade would just re-apply them.

5.B DB damaged (counts wrong in §4.3) — restore the §2.6 dump. Scale the writer down first, through git
only if Flux would fight it; for a short restore the Recreate deployment can be scaled by the executor
via cberg-agent with operator GO:
```bash
# 1. stop the writer (cberg-agent): kubectl -n home-automation scale deploy/teslamate --replicas=0
# 2. restore into the existing DB, dropping objects first:
kubectl -n home-automation exec -i deploy/teslamate-postgres -- sh -c \
  'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' < "$DUMP"
# 3. re-run the §2.4 query: counts must equal the §2.4 baseline exactly, mig_max=20260808090000, type=range
# 4. revert the image (5.A) and wait for the HR to reconcile to 4.3.0
# 5. scale the writer back (cberg-agent): kubectl -n home-automation scale deploy/teslamate --replicas=1
#    (do NOT rely on Flux for this: the HR has no driftDetection, so a manual scale is not reverted)
```
Local `pg_restore` exists at `/opt/homebrew/bin/pg_restore` (for the §2.6 list check).
Data written between the dump and the restore (at most a few positions) is lost — acceptable only on
operator GO; the alternative is 5.C.

5.C Volume-level contingency: restore `teslamate-db` from the newest Completed Longhorn backup
(§2.5 name) per `docs/sops/backup.md` / `docs/sops/longhorn.md` — operator-present only.

## 6) Interference notes

- **Single pod roll, no shared-infra restart.** Postgres is not restarted; Grafana is not restarted
  (its TeslaMate dashboards are already fetched from upstream `master`, unrelated to this bump).
  Expect a ~30-60 s 503 on the internal route and a short gap in logging.
- **Do not run during a drive or charge** (§2.3) — the Recreate would split it into two records.
- **conflicts_with:** `helm-drift-detection` and `flux-oci-chart-sources` both rewrite
  `helmrelease/teslamate` (same object). No kube-prometheus-stack, grafana or mosquitto plan is open
  on 2026-10-25; §4.5/§4.7 read Grafana and Prometheus, so any such plan scheduled into the same
  night must be added here (and list this plan) before vetting.
- **Repo correction (not done here, out of scope):** the 11 TeslaMate dashboards in
  `kubernetes/apps/monitoring/grafana/app/helmrelease.yaml` are pulled from unpinned
  `teslamate-org/teslamate/master`, so every Grafana restart can silently pull dashboards written
  for a NEWER schema than the deployed app. Pinning those URLs to the deployed tag (`v4.4.0`) in
  lockstep with the image would remove that drift; it belongs in its own change.
- Tesla API tokens refresh every 6 h; a restart refreshes immediately (`Refreshed api tokens`), no
  re-login needed — the encrypted tokens live in the DB under `ENCRYPTION_KEY` (unchanged Secret
  `teslamate-secret`).
