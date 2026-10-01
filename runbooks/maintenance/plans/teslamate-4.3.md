---
plan_id: teslamate-4.3
component: teslamate
pr: null                              # no open Renovate PR (gh pr list --search teslamate: empty,
                                      # 2026-09-30). Dispatched by maintenance-window nightly
                                      # 2026-09-30 Step 0.5 from coverage.py (lane=PLAN).
kind: image
current: "4.2.0"                      # live 2026-09-30: pod teslamate-694c57c9b4-* imageID
                                      # docker.io/teslamate/teslamate@sha256:88f4b0eb20802e4dd8518b31045d2c19ce384bd5c85ae7289a921f5221ea2562
                                      # = Docker Hub digest of tags 4.2.0 AND 4.2 (same index).
target: "4.3.0"                       # the held target was the FLOAT "4.3". Resolved by digest-compare
                                      # on Docker Hub 2026-09-30: tags 4.3, 4.3.0 and latest ALL =
                                      # sha256:516fc9f0a14369f541b1a70ff2f65dd9b57c2e01c1f533b6d43b375445404955
                                      # (multi-arch index: amd64 + arm64, both status active).
                                      # 4.3.0 is a GA GitHub release (v4.3.0, 2026-09-29, prerelease=false).
                                      # This plan pins the FIXED tag 4.3.0 + that index digest, never "4.3".
update_type: minor
risk: low                             # §1: ZERO new DB migrations (migration sets of v4.2.0 and v4.3.0
                                      # are byte-for-byte the same 106 file names; live schema_migrations
                                      # max = 20260808090000 = the newest file in both), same Dockerfile
                                      # user/entrypoint shape, MQTT HA-discovery (the one area with a
                                      # behaviour note) is OFF here. Main moving part is the rewritten
                                      # startup DB wait (#5800) — exercised on every start, so §4 sees it.
est_duration_min: 25                  # pre-checks 6 + edit/commit/push/Flux ~4 + Recreate/pull/boot ~3
                                      # + gates 4.1-4.6 ~7 + 10 min settle (waited, not worked) — slack ~5
needs_reboot: false
touches:
  namespaces: [home-automation]
  resources:
    - helmrelease/teslamate           # image.tag edit — the ONLY git change
    - deployment/teslamate            # ONE Recreate roll (strategy verified live: Recreate)
    - service/teslamate               # not edited; backend of httproute/teslamate (4000)
    - httproute/teslamate             # not edited; envoy-internal, ~1-2 min 503 during the roll
    - deployment/teslamate-postgres   # NOT rolled; READ by §2/§4 (psql SELECTs only). TeslaMate runs
                                      # its migrator against it on boot (0 pending — asserted in §4.3)
    - pvc/teslamate-db                # not edited; longhorn-static, Retain; restore floor in §5.2
    - secret/teslamate-secret         # not edited; consumed as before
  shared: [mqtt]                      # TeslaMate reconnects to mosquitto-internal on restart and
                                      # republishes its retained teslamate/cars/1/* topics (as on any
                                      # restart). No gateway change (route untouched), no Authentik,
                                      # grafana's TeslaMate datasource only READS the same DB.
depends_on: []
conflicts_with:
  - app-template-5.2.1                # Batch A sed edits the SAME file (teslamate/app/helmrelease.yaml,
                                      #   chart line) and upgrades the SAME HR. Its Batch A change is label-only
                                      #   (rendered objects identical but the chart label), so IT does not roll
                                      #   teslamate — but this plan DOES, and its §4 whole-fleet generation gate
                                      #   would read our roll as GEN_CHANGED; two writers on one file/HR in one
                                      #   night also make either §4 unattributable. Reciprocal entry added there.
  - helm-drift-detection              # adds spec.driftDetection to every HR incl. helmrelease/teslamate
  - flux-reconciler-impersonation     # changes the identity helm-controller applies home-automation/ with
  - flux-oci-chart-sources            # rewrites HR chart sources (bjw-s app-template) — same spec.chart block
  - kube-prometheus-stack-91.4.1      # §4.5 reads kube-state-metrics through Prometheus (the window's
                                      #   instrument). Executed 2026-09-26; kept so a re-run/revert serializes.
  - talos-linux-1.14.2                # node roll (exclusive, sun-attended) reschedules every pod incl.
                                      #   teslamate + teslamate-postgres; a same-slot roll would void §4.2-4.6.
                                      #   exclusive:true already keeps it out of the slot; named for the record.
exclusive: false
security_ref: F-7d7fb365              # AR-029 record on the 4.2.0 image ("already on newest tag"). A newer
                                      # tag now exists, so that acceptance's premise lapses and this bump is
                                      # its remedy. Its twin F-50167e66 (AR-029, 4.2.0, the no-upstream-fix
                                      # subset) is the same image's other record and is re-evaluated by the
                                      # first sweep after the bump. Detail stays on the records — nothing here.
capability_change: true               # HONEST, not "to be safe". 4.3.0 adds: two new GET routes
                                      # (/notice, /license — router.ex, PR #5779), a new settings-page
                                      # control that reorders vehicles (#5741) and a settings-page action
                                      # that starts loggers for newly-assigned vehicles without a restart
                                      # (#5710). All small and all behind the LAN-only envoy-internal route,
                                      # but they are new routes/features, which the rule defines as true.
                                      # Consequence: HUMAN-GATED — needs an operator GO; not SD-10.
rollback_class: git-revert            # nothing forward-only: 0 migrations (§1, asserted in §4.3), no PV/
                                      # volumeHandle change, no on-disk state in the teslamate pod (emptyDir
                                      # /tmp only). If §4.3 finds an UNEXPECTED migration, §5.2 is the
                                      # restore procedure (Longhorn backup of teslamate-db taken 03:00 same night).
finding_refs: []                      # `policy-cli.py finding list --grep teslamate` (2026-09-30) has NO row for
                                      # the image 4.2.0 -> 4.3 bump (4.3.0 published 2026-09-29 14:34Z, after the
                                      # last sweep). F-8abf3da3 / F-65436d0a are the CHART 5.1.0->5.2.1 rows,
                                      # owned by app-template-5.2.1, not this plan.
review: null
status: draft
window: null
premises:
  - id: live-image-is-4.2.0
    why: >-
      current and the rollback target assume the running teslamate container is
      the 4.2.0 index digest. If a Step 0 lane or a hand edit already moved it,
      this plan is stale.
    run: kubectl get pod -n home-automation -l app.kubernetes.io/instance=teslamate -o jsonpath='{.items[*].status.containerStatuses[*].imageID}'
    expect_contains: "sha256:88f4b0eb20802e4dd8518b31045d2c19ce384bd5c85ae7289a921f5221ea2562"
  - id: manifest-pin-4.2.0-once
    why: >-
      §3 replaces exactly this line. If it is gone or duplicated, the sed in §3
      is wrong (dry-tested against a one-hit file).
    run: grep -c '^              tag. "4.2.0"$' kubernetes/apps/home-automation/teslamate/app/helmrelease.yaml
    expect_exact: "1"
  - id: hr-ready
    why: A reconcile already failing would make the §4.1 gate unattributable.
    run: kubectl get helmrelease -n home-automation teslamate -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: db-available
    why: >-
      4.3.0's new entrypoint waits for the DB WITHOUT a time limit (#5800). With
      the DB down the pod never serves, the liveness probe kills it and the gate
      fails for a reason unrelated to the bump.
    run: kubectl get deploy -n home-automation teslamate-postgres -o jsonpath='{.status.availableReplicas}'
    expect_exact: "1"
  - id: db-engine-unchanged
    why: >-
      The zero-migration analysis and the §5.2 restore floor assume postgres 18.6
      behind teslamate-postgres; a same-night DB engine change would confound both.
    run: kubectl get deploy -n home-automation teslamate-postgres -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "postgres:18.6"
  - id: ha-discovery-off
    why: >-
      The only behaviour note in the 4.3.0 release concerns opt-in MQTT HA
      discovery (MQTT_HOME_ASSISTANT_DISCOVERY=true). risk low rests on it being
      unset here; if someone enabled it, re-plan the HA-entity side.
    run: kubectl get deploy -n home-automation teslamate -o jsonpath='{.spec.template.spec.containers[0].env[*].name}'
    expect_matches: '^(?!.*MQTT_HOME_ASSISTANT_DISCOVERY).*MQTT_HOST.*$'
  - id: db-volume-backup-enrolled
    why: >-
      §5.2 (the unexpected-migration contingency) restores from the nightly
      Longhorn backup of teslamate-db. It only exists if the volume is in the
      default recurring-job group. Freshness is checked in §2.3 (a premise
      cannot compare dates).
    run: kubectl get volume -n storage teslamate-db -o jsonpath='{.metadata.labels}'
    expect_contains: "recurring-job-group.longhorn.io/default"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/longhorn.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-09-30"
---

# teslamate image 4.2.0 -> 4.3.0 (held as float "4.3")

## 1. Summary & why held

**Change:** in `kubernetes/apps/home-automation/teslamate/app/helmrelease.yaml`,
`controllers.main.containers.main.image.tag` `"4.2.0"` ->
`"4.3.0@sha256:516fc9f0a14369f541b1a70ff2f65dd9b57c2e01c1f533b6d43b375445404955"`.
Nothing else. `teslamate-postgres` (postgres 18.6), the secret, the route and the
chart (app-template 5.1.0) are untouched.

**Why held:** coverage saw target `4.3`, which names fewer version components
than the pin `4.2.0` — a floating series pointer that cannot be shown to be GA.
**Resolved (Docker Hub tag API, 2026-09-30):**

| tag | index digest | last_updated |
|---|---|---|
| `4.3` | `sha256:516fc9f0…404955` | 2026-09-29T14:34:00Z |
| `4.3.0` | `sha256:516fc9f0…404955` | 2026-09-29T14:33:58Z |
| `latest` | `sha256:516fc9f0…404955` | 2026-09-29T14:34:01Z |
| `4.2.0` / `4.2` (live) | `sha256:88f4b0eb…2ea2562` | 2026-08-23 |

`4.3` currently points at `4.3.0`, which is the GA GitHub release `v4.3.0`
(published 2026-09-29, `prerelease: false`). The index has amd64 + arm64
manifests; all three nodes are amd64. The plan pins the **fixed tag plus the
index digest** (same form as `traccar` 6.16.0), so a later move of `4.3` to
4.3.1 cannot silently change what runs.

**Upstream evidence (v4.3.0 release notes + source):**

- **DB migrations: none.** The migration directory moved
  (`priv/repo/migrations` -> `elixir/priv/repo/migrations`, #5745 "move the
  Elixir application to `elixir/`"), but the file sets at `v4.2.0` and `v4.3.0`
  are identical: 106 names, `diff` empty, newest
  `20260808090000_recalc_charge_energy_used.exs`. The live DB already has
  `schema_migrations` max = `20260808090000` (105 rows). So the boot-time
  migrator has nothing to apply — the concern in the dispatch brief (forward-only
  migration) does not arise for this step. §4.3 asserts it anyway.
- **Startup changed (#5800, "fix(docker): start with a PostgreSQL that is
  reachable only through its Unix socket"):** the entrypoint's `nc -z` loop is
  gone; `bin/teslamate eval "TeslaMate.Release.wait_for_database_and_migrate()"`
  now probes with `SELECT 1` through Ecto and "waits without a time limit";
  `netcat-openbsd` is removed from the image. We use TCP (`DATABASE_HOST=
  teslamate-postgres`, port default `5432` in `runtime.exs`), which the PR's
  state table lists as supported. Failure shape if it went wrong: pod never
  becomes Ready, logs repeat `Waiting for the database to accept connections`.
- **Image shape unchanged:** Dockerfile `USER nonroot:nonroot`, same
  `groupadd --gid 10001` / `useradd --uid 10000`, same
  `ENTRYPOINT ["tini", "--", "/bin/dash", "/entrypoint.sh"]`, same
  `CMD ["bin/teslamate", "start"]`, `EXPOSE 4000`, files `--chmod=555`. Our pod
  `runAsUser: 10001` runs 4.2.0 on this exact layout today, so the 7d
  root-entrypoint class (`application-update.md` §7d) does not apply.
- **MQTT HA discovery note:** "TeslaMate no longer re-runs the discovery
  migration on every restart … Upgrading directly from 4.1.x no longer preserves
  entity registry customizations". Discovery is opt-in via
  `MQTT_HOME_ASSISTANT_DISCOVERY=true` (`runtime.exs` L199); it is **not set**
  here (premise `ha-discovery-off`), and we come from 4.2.0, not 4.1.x.
- **Auth (#5781):** token refresh "no longer follow[s] redirects". Correct-
  direction hardening; if Tesla's refresh endpoint ever redirected for us, the
  refresh would fail. Refresh **does happen at boot** — measured on the live
  4.2.0 pod's full log (started 2026-09-28): `POST https://auth.tesla.com/oauth2/v3/token
  -> 200`, `Refreshed api tokens`, `Scheduling token refresh in 6 h`, all within
  3 s of `Version: 4.2.0`. So the #5781 path is exercised in the window and is
  gated by §4.6 (presence of `Refreshed api tokens`); §4.7 keeps only the 6 h
  scheduled refresh + positions soak.
- **Grafana:** "use Grafana 13.2.2" and the new temperatures dashboard concern
  the separate `teslamate/grafana` image and the repo's dashboard JSON. We run
  neither: our grafana (ns monitoring) pulls 8 TeslaMate dashboards from
  `teslamate/master/grafana/dashboards/*.json` (still HTTP 200 after the
  `elixir/` move, checked 2026-09-30) independent of this image.

**capability_change: true** — see the frontmatter: two new static GET routes and
two new settings-page actions. Small and LAN-only, but new, so this plan is
human-gated. Risk stays low.

## 2. Pre-checks

Run from `/Users/mu/code/cberg-home-nextgen` (zsh). Premises are re-checked by the
window agent first (`plan-premises.py teslamate-4.3`).

2.1 Target still resolves to the pinned digest (a retag between planning and
execution means re-plan, not "use the new digest"):
```bash
curl -s https://hub.docker.com/v2/repositories/teslamate/teslamate/tags/4.3.0 |
  python3 -c "import sys,json;d=json.load(sys.stdin);print(d['digest'])"
# PASS: sha256:516fc9f0a14369f541b1a70ff2f65dd9b57c2e01c1f533b6d43b375445404955 ; anything else -> STOP
```

2.2 Baseline (DB contents + web contents), saved for §4:
```bash
kubectl -n home-automation exec deploy/teslamate-postgres -- sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select count(*)||'"'"' '"'"'||max(version) from schema_migrations; select count(*) from positions; select count(*) from drives; select count(*) from charging_processes; select count(*) from cars;"' \
  | tee /tmp/teslamate-baseline.txt
# measured 2026-09-30: "105 20260808090000" / 4216509 / 1672 / 357 / 1
```
FAIL here (psql error, empty file) -> STOP; the §4.3 gate would have no baseline.

2.3 Tonight's Longhorn backup of `teslamate-db` exists (the 03:00
`daily-backup-all-volumes` RecurringJob; last three measured Completed at
03:03-03:05 on 09-27/28/29). Newest Backup CR must be Completed and < 26 h old:
```bash
kubectl get backups.longhorn.io -n storage \
  -o 'custom-columns=N:.metadata.name,VOL:.status.volumeName,STATE:.status.state,AT:.status.backupCreatedAt' \
  | grep ' teslamate-db ' | sort -k4 | tail -1
# PASS: STATE=Completed and AT within the last 26 h. If tonight's is still InProgress, wait for it.
# (lastBackupAt on the Volume can lag one cycle — docs/sops/backup.md; read the Backup CR.)
```

2.4 Pod healthy, no restarts, Flux clean:
```bash
kubectl -n home-automation get pod -l app.kubernetes.io/instance=teslamate \
  -o 'custom-columns=N:.metadata.name,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount'
flux get helmreleases -n home-automation teslamate teslamate-postgres
```

2.5 Web baseline (the §4.4 markers must be present BEFORE, or that gate cannot
distinguish anything):
```bash
kubectl -n home-automation port-forward svc/teslamate 14000:4000 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s -o /tmp/tm-before.html -w '%{http_code}\n' http://localhost:14000/
grep -c -i 'Range (rated)' /tmp/tm-before.html   # measured 2026-09-30: HTTP 200, count >= 1
kill $PF 2>/dev/null
```

2.6 Silence + marker (`application-update.md` Step 1):
```bash
runbooks/update-marker.sh add teslamate home-automation 2 "teslamate 4.2.0->4.3.0"
```
(Alertmanager silence per SOP Step 1 with `namespace=home-automation`,
`alertname=~Kube(Pod|Deployment).*`, TTL 2h — TeslaMate has no app-specific alerts.)

## 3. Steps

3.1 Edit the pin (dry-tested on a scratch copy with BSD sed on macOS; the
resulting diff is exactly one line, and the file still parses as YAML):
```bash
sed -i '' 's|^              tag: "4.2.0"$|              tag: "4.3.0@sha256:516fc9f0a14369f541b1a70ff2f65dd9b57c2e01c1f533b6d43b375445404955"|' \
  kubernetes/apps/home-automation/teslamate/app/helmrelease.yaml
git diff kubernetes/apps/home-automation/teslamate/app/helmrelease.yaml
```
Expected diff (from the dry run):
```
36c36
<               tag: "4.2.0"
---
>               tag: "4.3.0@sha256:516fc9f0a14369f541b1a70ff2f65dd9b57c2e01c1f533b6d43b375445404955"
```
Anything else in the diff -> `git checkout -- <file>` and STOP.

3.2 Commit only this file, verify, push:
```bash
cat > /tmp/teslamate-msg.txt <<'EOF'
chore(teslamate): bump image 4.2.0 -> 4.3.0 (plan teslamate-4.3)

Held target was the float "4.3"; resolved by digest to the GA tag 4.3.0
(index sha256:516fc9f0...) and pinned to tag+digest. No DB migrations
between v4.2.0 and v4.3.0 (identical migration sets).

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
git commit --only kubernetes/apps/home-automation/teslamate/app/helmrelease.yaml -F /tmp/teslamate-msg.txt
git log -1 --format=%s        # must be the subject above; amend before push if not
git show --stat HEAD          # exactly one file
git push
```
Flux webhook reconciles. No manual `flux reconcile` (SOP default). Deployment
strategy is `Recreate` (verified live), so there is a ~1-2 min gap with no pod —
expected. Do not delete pods by hand mid-Recreate.

## 4. Verification

Run 4.1-4.6 in order, starting once the HR reports the new revision (allow up to
10 min for the webhook + pull). Any FAIL -> §5.

**4.1 HR upgraded:**
```bash
kubectl get helmrelease -n home-automation teslamate -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.conditions[?(@.type=="Ready")].message}{"\n"}'
```
PASS: `True` and message names a NEW `teslamate.vNN` (> v26, live 2026-09-30).
Guards against: a failed upgrade (Ready False / "upgrade retries exhausted").

**4.2 The new bytes run (imageID, not tag — `feedback_rollout_status_old_generation`):**
```bash
kubectl get pod -n home-automation -l app.kubernetes.io/instance=teslamate \
  -o 'jsonpath={range .items[*]}{.metadata.name} {.status.containerStatuses[0].imageID} {.status.containerStatuses[0].ready}{"\n"}{end}'
```
PASS: exactly one pod, imageID ends `sha256:516fc9f0a14369f541b1a70ff2f65dd9b57c2e01c1f533b6d43b375445404955`, ready `true`.
Guards against: the old pod still serving (rollout read against the old
generation) — would print `…88f4b0eb…`.

**4.3 CONTENTS ASSERTION: the DB is unchanged in schema and not lost rows** —
measured by re-running the §2.2 query, compared to `/tmp/teslamate-baseline.txt`:
```bash
kubectl -n home-automation exec deploy/teslamate-postgres -- sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select count(*)||'"'"' '"'"'||max(version) from schema_migrations; select count(*) from positions; select count(*) from drives; select count(*) from charging_processes; select count(*) from cars;"' \
  > /tmp/teslamate-after.txt
python3 - <<'PY'
b=open('/tmp/teslamate-baseline.txt').read().split('\n'); a=open('/tmp/teslamate-after.txt').read().split('\n')
ok = a[0]==b[0] and all(int(a[i])>=int(b[i])>0 for i in (1,2,3)) and a[4]==b[4]
print('PASS' if ok else f'FAIL before={b[:5]} after={a[:5]}')
PY
```
PASS: line 1 identical (`105 20260808090000` — no migration ran), positions/
drives/charging_processes each >= baseline AND > 0, cars identical.
Guards against: an unexpected migration (line 1 differs -> go to **§5.2**, not
§5.1), a pointed-at-empty DB (counts 0), data loss (counts drop). Can it fail? Yes
— the `>0` floor fails on an empty DB, the string compare on any migration.

**4.4 CONTENTS ASSERTION: the web UI renders the logged vehicle, not a sign-in
page or the new "no vehicle is logged" explanation** — measured by fetching `/`
and grepping the summary-card labels, compared to the §2.5 baseline:
```bash
kubectl -n home-automation port-forward svc/teslamate 14000:4000 >/dev/null 2>&1 & PF=$!; sleep 3
code=$(curl -s -o /tmp/tm-after.html -w '%{http_code}' http://localhost:14000/)
hits=$(grep -c -i 'Range (rated)' /tmp/tm-after.html)
signin=$(grep -c -i 'sign_in' /tmp/tm-after.html)
kill $PF 2>/dev/null
echo "code=$code summary_hits=$hits signin=$signin"
```
PASS: `code=200`, `summary_hits>=1`, `signin=0`. `Range (rated)` is rendered
only inside a vehicle summary card (measured 2026-09-30 on 4.2.0: 1 hit on `/`,
**0 hits on `/sign_in`** — negative control run. `Mileage` was deliberately NOT
used: it also appears in the navbar's Grafana-dashboard link on every page,
including `/sign_in`, so it could never fail). Guards against: revoked/
unreadable tokens (redirect to `/sign_in` — `code=302` or signin>0), the vehicle
process not started (#5710's "no vehicle is logged" page carries no summary card
-> hits=0), and a 500. Case-insensitive on purpose (upstream label casing).

**4.5 Stays up — no crash loop over 10 min.**
CONTROL: metric kube_pod_container_status_restarts_total — `{namespace="home-automation",container="main",pod=~"teslamate-[0-9a-f]+-.*"}` for the NEW pod must be `0` at T+10 min (live 2026-09-30: 1 series, value 0 for the 4.2.0 pod).
CONTROL: metric kube_deployment_status_replicas_available — `{namespace="home-automation",deployment="teslamate"}` must be `1` at T+10 min (live: 1 series, value 1).
CONTROL: metric kube_pod_container_info — `{namespace="home-automation",pod=~"teslamate-[0-9a-f]+-.*"}` must carry `image_id` ending `516fc9f0…404955` (the Prometheus-side twin of 4.2).
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
for q in 'kube_pod_container_status_restarts_total{namespace="home-automation",container="main",pod=~"teslamate-[0-9a-f]+-.*"}' \
         'kube_deployment_status_replicas_available{namespace="home-automation",deployment="teslamate"}' \
         'kube_pod_container_info{namespace="home-automation",pod=~"teslamate-[0-9a-f]+-.*"}'; do
  curl -s -G http://localhost:19090/api/v1/query --data-urlencode "query=$q" |
    python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print(len(r),[(x['metric'].get('image_id') or x['metric'].get('pod'),x['value'][1]) for x in r])"
done
kill $PF 2>/dev/null
```
PASS: each query returns >= 1 series (an EMPTY result is a FAIL — it means the
selector/metric is wrong, not that all is well); restarts `0` for the new pod,
available `1`, image_id `…516fc9f0…`. Expect the OLD pod's restart series to
linger in the first query for a few minutes — judge by the new pod name.

**4.6 CONTENTS ASSERTION: the boot reached each milestone on 4.3.0** — measured
on the NEW pod's FULL log (no `--since`: the boot lines are written once, in the
first ~3 s, and a `--since` window started later silently drops them, turning
an absence grep into a gate that cannot fail). Pod name from §4.2:
```bash
NEWPOD=$(kubectl get pod -n home-automation -l app.kubernetes.io/instance=teslamate -o jsonpath='{.items[0].metadata.name}')
kubectl -n home-automation logs "$NEWPOD" -c main > /tmp/tm-boot.log
wc -l < /tmp/tm-boot.log                                   # must be > 0 (empty log = FAIL, not PASS)
for p in 'Version: 4.3.0' 'Migrations already up' 'Running TeslaMateWeb.Endpoint' 'Refreshed api tokens'; do
  printf '%s => %s\n' "$p" "$(grep -c -i -F "$p" /tmp/tm-boot.log)"
done
# secondary (absence) pattern:
grep -i -c -E 'waiting for the database|\*\* \(|terminating|crash|exited' /tmp/tm-boot.log
```
PASS (primary, presence): `Version: 4.3.0` = **1**, `Migrations already up` =
**1**, `Running TeslaMateWeb.Endpoint` = **1**, `Refreshed api tokens` **>= 1**.
Measured on the live 4.2.0 pod (full log, 67 780 lines, pod started
2026-09-28): `Version: ` 1 (as `Version: 4.2.0`), `Migrations already up` 1,
`Running TeslaMateWeb.Endpoint` 1, `Refreshed api tokens` 1 — so each marker is
emitted exactly once per boot and the strings exist upstream. Each can fail:
- `Version: 4.3.0` = 0 -> the old image/old pod is being read (prints `Version:
  4.2.0`) or the app never got past release start;
- `Migrations already up` = 0 -> the #5800 `wait_for_database_and_migrate` path
  either ran a migration (logs `Migrated …` instead — cross-check §4.3, go to
  §5.2) or never connected;
- `Running TeslaMateWeb.Endpoint` = 0 -> the web endpoint did not start;
- `Refreshed api tokens` = 0 -> the #5781 refresh failed at boot (look for
  `oauth2/v3/token` with a non-200 / a refresh error in the same file) -> §5.1.
Counts > 1 for the first three mean the container restarted and `logs` shows a
later boot — read §4.5's restart count.
PASS (secondary, absence): `0`. Guards against the DB wait loop (`Waiting for the
database`) and OTP crash reports (`** (`, `terminating`). The recurring Tesla-
side `[warning] TeslaApi.Error … timeout / vehicle not connected` and
`car_id=1 [error] Error / :unknown` lines are pre-existing API-side noise and
deliberately NOT in this pattern.

**4.7 Post-window soak (non-gating, next sweep):** the boot refresh is already
gated in §4.6; here only (a) the first SCHEDULED refresh, 6 h after boot, and
(b) `positions` max(date) advancing after the car's next drive. The scheduled
refresh does NOT log `Refreshed api tokens` (that line is boot-only — measured on
the 4.2.0 pod over 3 days: 1x `Refreshed api tokens`, 11x `Refreshing access
token ...`, 12x `POST https://auth.tesla.com/oauth2/v3/token -> 200`), so read:
```bash
kubectl -n home-automation logs "$NEWPOD" -c main > /tmp/tm-soak.log
grep -c -i -F 'Refreshing access token' /tmp/tm-soak.log                       # >= 1 after T+6h
grep -i -F 'oauth2/v3/token' /tmp/tm-soak.log | grep -c -v -E -- '-> 200 '      # 0 (any non-200 token POST = FAIL)
```
Report in the morning summary; a failure here is §5.1.

Then: clear marker (`runbooks/update-marker.sh clear teslamate`), expire the silence.

## 5. Rollback

**5.1 Normal rollback (git revert — nothing forward-only happened; §4.3 line 1 unchanged):**
```bash
git revert --no-edit <sha-of-3.2-commit>
git log -1 --format=%s && git show --stat HEAD   # one file, the helmrelease
git push
```
Confirm back: re-run 4.2 — imageID ends `sha256:88f4b0eb20802e4dd8518b31045d2c19ce384bd5c85ae7289a921f5221ea2562`,
ready `true`; re-run 4.3 and 4.4 against the baseline — PASS. 4.2.0 boots on the
same schema (no migration ran), so no DB action is needed.

**5.2 Contingency — §4.3 showed a CHANGED `schema_migrations` line** (not
expected per §1; means upstream shipped something the file-set diff did not show):
1. Do NOT simply revert — 4.2.0 against a migrated schema is untested. First
   suspend the app so it stops writing:
   `flux suspend helmrelease -n home-automation teslamate` is a cluster mutation —
   delegate to cberg-agent, together with scaling `deployment/teslamate` to 0.
2. Capture what ran: `select version, inserted_at from schema_migrations order by version desc limit 5;`
   and record it on the plan's report.
3. Decide with the operator (attended): either stay on 4.3.0 (resume; the
   forward state is upstream-supported) — the default, since the app was healthy
   by 4.4/4.5 — or restore `teslamate-db` from the Backup CR recorded in §2.3 via
   `docs/sops/backup.md` "Restore from Backup" (restore the Longhorn volume from
   that backup, re-bind per "Bind Restored Volume to Application"; PV
   `teslamate-db` is `longhorn-static`, `Retain`, volumeHandle `teslamate-db`),
   then §5.1's revert. Data logged between 03:00 and the restore is lost —
   operator call, never unattended.

## 6. Interference notes

- **Same HR file as `app-template-5.2.1`** (Batch A): its sed touches the chart
  line, this plan the image line. Textually compatible. Its Batch A change is
  label-only and does not roll teslamate, but this plan rolls it, and that
  plan's §4 whole-fleet generation gate would print `GEN_CHANGED
  home-automation/deployment/teslamate`; two upgrades of one HR in one night also
  blur both plans' attribution. Never the same night; reciprocal
  `conflicts_with` entry added to `app-template-5.2.1.md` (2026-10-01).
- **`talos-linux-1.14.2`** (exclusive, sun-attended, three node reboots) would
  reschedule teslamate and teslamate-postgres; never the same slot. Its
  `exclusive: true` enforces this; listed in `conflicts_with` for the record.
- `helm-drift-detection`, `flux-reconciler-impersonation`, `flux-oci-chart-sources`
  all rewrite how/what helm-controller applies to this HR — serialized via
  `conflicts_with`.
- **Nightly 03:30 vs the 03:00 backup:** the backup of `teslamate-db` finishes
  ~03:05 (measured three nights). §2.3 makes the plan wait for it rather than
  push during a snapshot.
- **MQTT:** restart republishes retained `teslamate/*` topics to
  mosquitto-internal — identical to any pod restart; HA discovery is off. Do not
  pair with a mosquitto change the same night (none open today).
- **Grafana** reads the same DB via datasource `TeslaMate`; no change there. The
  §4.5 gate reads Prometheus — hence `kube-prometheus-stack-91.4.1` in
  `conflicts_with`.
- Human-gated because `capability_change: true` (new routes/settings actions);
  interruption is ~2 min of the LAN-only UI and a gap in position logging, which
  at 03:30 with the car parked loses nothing.
