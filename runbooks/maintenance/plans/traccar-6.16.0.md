---
plan_id: traccar-6.16.0
component: traccar
pr: null                              # No Renovate PR. Surfaced by version-check as the FLOATING
                                      # `6.16`; coverage.py's ARITY detector held it (a 2-component
                                      # series pointer replacing the fixed 3-component pin 6.15.3).
kind: image
current: "6.15.3"                     # live-verified 2026-09-27: deploy image traccar/traccar:6.15.3,
                                      # pod imageID docker.io/traccar/traccar@sha256:35346b4a...,
                                      # /api/server reports version 6.15.3
target: "6.16.0@sha256:03ebb7ed2b219d4f25c326873bd022f5062f80bcae622a9d9422846b51951eda (fixed pin replacing the floating 6.16)"
                                      # Leading 6.16.0 = what gets pinned. Trailing bare 6.16 keeps
                                      # plan_matching.target_covers() matching the held `new: 6.16`
                                      # (version tokens: {"6.16.0"} alone does NOT intersect {"6.16"}).
                                      # Digest = the multi-arch OCI index; on 2026-09-27 Docker Hub
                                      # serves the IDENTICAL index digest for 6.16.0, 6.16, 6, latest.
update_type: minor
risk: low                             # schema changelog + Dockerfile byte-identical to 6.15.3 (§1);
                                      # the three behaviour changes that could bite were measured
                                      # against live data and hit 0 rows. Held for the float, not
                                      # for the software.
est_duration_min: 95                  # ~15 active (pre-checks, dump, push, roll ~2 min outage) +
                                      # up to 80 min for §4.3 (45 min wait + INCONCLUSIVE extension,
                                      # capped so the whole plan stays inside the window; beyond
                                      # that it goes awaiting-soak). Night ingest is ~4-12 positions/h.
needs_reboot: false
touches:
  namespaces: [home-automation]
  resources:
    - helmrelease/traccar             # image tag edit (the only git change)
    - deployment/traccar              # strategy Recreate -> ~1-2 min full outage of UI/API + osmand
    - service/traccar-osmand          # NOT edited; LB 192.168.55.31:5055 has no endpoint during the roll
    - service/traccar-main            # NOT edited; backend of HTTPRoute/traccar (envoy-external)
    - httproute/traccar               # NOT edited; public hostname 503s for the outage only
    - deployment/traccar-postgres     # NOT edited; Liquibase connects + checks changelog on start
    - pvc/traccar-postgres-data       # read (pg_dump) only
  shared: []                          # envoy-external is not reconfigured (route unchanged) — only
                                      # this app's backend blips; LB-IPAM IP unchanged; DB is
                                      # dedicated (not a shared postgres). External consumer:
                                      # findmy-traccar-sync on the Mac mini (retries failed uploads).
depends_on: []
conflicts_with: [flux-reconciler-impersonation, flux-oci-chart-sources, helm-drift-detection, kube-prometheus-stack-91.4.1, chart-patches-coredns-reloader-blackbox]
# PARKED 2026-09-27: app-template-5.2.1 is an uncommitted draft from another session (DEAD-REF on main); re-add to conflicts_with once it lands.
                                      # flux-reconciler-impersonation: changes how kustomize/helm-
                                      #   controller apply in home-automation (and is exclusive).
                                      # flux-oci-chart-sources: repoints the bjw-s chart source this
                                      #   HelmRelease renders from; a same-night move makes a failed
                                      #   upgrade here ambiguous.
                                      # helm-drift-detection: adds a spec field to every HelmRelease
                                      #   incl. helmrelease/traccar — two writers, one object.
                                      # kube-prometheus-stack-91.4.1: §4 reads findmy_sync_* through
                                      #   Prometheus — the window's instrument (executed today; kept
                                      #   so a re-run/revert of it is still serialized).
                                      # chart-patches-coredns-reloader-blackbox: rolls CoreDNS; traccar
                                      #   resolves traccar-postgres by DNS at JDBC connect on startup,
                                      #   and §4.5 reads Prometheus — a same-night DNS roll makes a
                                      #   failed start here unattributable.
                                      # app-template-5.2.1: its Batch A seds the chart version in
                                      #   helmrelease/traccar (same file this plan edits) — two
                                      #   writers, one file, one reconcile.
exclusive: false
security_ref: F-10584021              # image-CVE driver on 6.15.3. PARTIAL remediation only —
                                      # the residual on 6.16.0 is recorded on the finding, not here.
capability_change: false              # Find Hub command sender now default-off (0 devices use it),
                                      # device-id validation (0 invalid ids) — no used behaviour moves
rollback_class: git-revert            # valid ONLY because 6.16.0 ships no Liquibase changeset
                                      # (§1, proven again post-roll by the §4.2 DATABASECHANGELOG
                                      # gate). If that gate fails, rollback becomes the §5.3
                                      # pg_restore procedure — the dump in §3.2 is taken regardless.
finding_refs: [F-36932ec1]            # "traccar: image traccar/traccar 6.15.3 → 6.16 (minor)"
status: vetted
window: null
premises:
  - id: live-image-still-6.15.3
    why: >-
      current and the rollback target assume 6.15.3 is what serves. If a Step 0
      direct-bump or a hand edit already moved it, the baseline and revert are wrong.
    run: kubectl get deploy -n home-automation traccar -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: traccar/traccar:6.15.3
  - id: manifest-pin-still-6.15.3
    why: "The §3.3 sed anchors on the exact string tag \"6.15.3\"; a changed pin makes it a silent no-op."
    run: cat /Users/mu/code/cberg-home-nextgen/kubernetes/apps/home-automation/traccar/app/helmrelease.yaml | grep -c 'tag. "6.15.3"'
    expect_exact: "1"
  - id: traccar-strategy-recreate
    why: >-
      The postgres PVC is RWO but traccar itself mounts no PVC; Recreate is what
      makes the outage bounded and prevents two Liquibase runners racing on the
      same DB at startup. If the chart default ever flipped to RollingUpdate the
      §4 outage/ingest reasoning changes.
    run: kubectl get deploy -n home-automation traccar -o jsonpath='{.spec.strategy.type}'
    expect_exact: Recreate
  - id: traccar-hr-ready
    why: "Do not stack an upgrade on a HelmRelease that is already failing."
    run: kubectl get helmrelease -n home-automation traccar -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: osmand-lb-ip
    why: "findmy-traccar-sync posts to the hard-coded http://192.168.55.31:5055; §4 probes that IP."
    run: kubectl get svc -n home-automation traccar-osmand -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
    expect_exact: 192.168.55.31
  - id: postgres-ready
    why: "Traccar runs Liquibase against traccar-postgres on start; the dump in §3.2 also needs it."
    run: kubectl get deploy -n home-automation traccar-postgres -o jsonpath='{.status.readyReplicas}'
    expect_exact: "1"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-09-27"
review: ready-for-go@2026-09-27   # plan-reviewer ready-for-go 2026-09-27 (7fff8d81 batch)
---

# traccar 6.15.3 → 6.16.0 (pinned by digest)

## 1. Summary & why held

Bump the Traccar server image in
`kubernetes/apps/home-automation/traccar/app/helmrelease.yaml` from
`traccar/traccar:6.15.3` to
`traccar/traccar:6.16.0@sha256:03ebb7ed2b219d4f25c326873bd022f5062f80bcae622a9d9422846b51951eda`.
app-template stays at 5.1.0 (the chart bumps F-ecd3db25 / F-159c75df are NOT in
scope). `traccar-postgres` (postgres 18.6) is not touched.

**Why it was held.** version-check offered the floating series tag `6.16`, and
`coverage.py`'s arity detector refuses any target with fewer version components
than the current fixed pin on the same major (it cannot be shown to be GA and a
reconcile can move it with no commit). That is the hold — not a known breaking
change. This plan pins the concrete release instead.

**Tag/digest evidence (2026-09-27, Docker Hub catalog + registry HEAD):**

| tag | index digest | pushed |
|---|---|---|
| `6.16.0` | `sha256:03ebb7ed…eda` | 2026-09-27T00:21:33Z |
| `6.16` | `sha256:03ebb7ed…eda` (identical) | 2026-09-27T00:21:35Z |
| `6.15.3` | `sha256:35346b4a…5df` (= live pod imageID) | — |

`6.16.0` is a non-prerelease GitHub release (`v6.16.0`, published
2026-09-27T00:20:15Z); `6.16.1` does not exist (404). The digest is an OCI
**image index** (`application/vnd.oci.image.index.v1+json`, amd64 + arm64), not
a per-platform manifest — pin that, per `application-update.md` Step 0b.

**Why a digest pin and not bare `6.16.0`.** The tag was pushed hours before
this plan was written; pinning the index digest freezes exactly the bytes that
were reviewed and scanned for this plan, and turns any later in-place rebuild of
`6.16.0` into a visible diff (Step 0b) instead of a silent change on the next
pod restart. It is house practice for app-template images (phpmyadmin,
memgraph, superset, sure-postgres), and `check-all-versions.py` strips the
`@sha256:` suffix (`_DIGEST_SUFFIX_RE`) so version tracking keeps working. Cost,
accepted: if upstream ever rebuilds the tag, Renovate raises a digest-type PR
that `auto-update.py` G1 holds for review.

**Upstream evidence — what changed v6.15.3 → v6.16.0.** The GitHub release body
is empty; the evidence is the tag comparison (96 commits):

- **No database migration.** `schema/` is byte-identical between the two tags
  (all 30 files, same git blob SHAs, `changelog-master.xml` identical — last
  include `changelog-6.15.0.xml`). Liquibase will connect, find 61 applied
  changesets (live `databasechangelog` = 61 rows, newest 2026-08-25) and apply
  none. This is why `rollback_class: git-revert` is honest here, and §4.2
  re-proves it after the roll.
- **Image layout unchanged.** `docker/Dockerfile.alpine` has the same blob SHA
  at both tags (`/opt/traccar`, jlinked JRE at `/opt/traccar/jre`,
  `tracker-server.jar`). Our HelmRelease overrides the entrypoint with a
  wrapper that runs `./jre/bin/java -jar tracker-server.jar conf/traccar.xml`
  and tails the file log; those paths still exist.
- **Behaviour changes that could touch this install, each checked against live data:**
  - *"Validate device identifiers"* (`db1ed43`): `Device.setUniqueId` now
    throws `IllegalArgumentException("Invalid device identifier")` for ids
    containing `/` or `\`, or equal to empty/`.`/`..`. Setters run when devices
    load from the DB, so one bad row could break device loading. Live: **0 of
    21 devices** match (§2.4 re-checks in-window).
  - *"Disable find hub by default"* (`b15554c`): the `findHub` command sender
    now needs `command.findHub.enable=true`. Live: **0 devices** carry a
    `findHub` attribute; our feed is the osmand protocol, not Find Hub.
  - *"Limit HTTP payload size"* (`51051d3`): only the Flespi and JimiPhoto
    aggregators changed (from unbounded to 1 MiB / 64 KiB+media buffer).
    OsmAnd, which is what we use, is not touched.
  - *"Preserve session expiration constraints"* (`3106d83`): token requests
    can no longer outlive the session's expiration. Basic-auth and form-login
    API use (what traccar-agent and §4 do) are unaffected.
  - *"Improve health check"* (`e7ebac0`): `/api/health` message-drop ratio
    fix. Our probes hit `/api/server`, not `/api/health`.
- Everything else is protocol-decoder fixes (Queclink, JT808, Xexun3, T800x…)
  and MCP tool changes — no device here uses those decoders.

**Security driver (partial).**

> **Security driver — detail withheld from this public repo.**
> Tracked as **F-10584021** (`security` / severity `warning`).
> Full detail (CVE IDs, counts, exposure, exploitability) lives on the
> finding record — it is deliberately not reproduced here.
>
> - Dashboard: `https://sweep.<DOMAIN>/findings/F-10584021`
> - CLI: `runbooks/policy-cli.py finding show F-10584021`
>
> See `docs/sops/vulnerability-disclosure.md` before adding any
> vulnerability detail to a committed file.

A back-to-back scan of both tags on 2026-09-27 shows this bump remediates
**part** of that finding, not all of it; the residual is upstream's to fix
(bump-not-rebuild rule). Do **not** close F-10584021 on this plan's execution —
let the next security sweep re-evaluate it against the running 6.16.0.

## 2. Pre-checks

Run from the repo root on the Mac mini (zsh).

```bash
cd /Users/mu/code/cberg-home-nextgen
NS=home-automation

# 2.1 Premises (read-only gate)
.venv/bin/python3 runbooks/plan-premises.py traccar-6.16.0

# 2.2 Target still exists and is still the reviewed bytes.
#     FAILS (prints a different digest / KeyError) if upstream re-tagged or deleted it.
curl -s "https://hub.docker.com/v2/repositories/traccar/traccar/tags/6.16.0" \
  | python3 -c "import sys,json;d=json.load(sys.stdin)['digest'];print(d);sys.exit(0 if d=='sha256:03ebb7ed2b219d4f25c326873bd022f5062f80bcae622a9d9422846b51951eda' else 1)" \
  && echo DIGEST_OK || echo "ABORT: 6.16.0 digest moved — re-review before pinning"

# 2.3 Flux + pods healthy, nothing mid-reconcile
flux get helmreleases -n $NS | grep -E '^NAME|traccar'          # both READY True
kubectl -n $NS get pods -l 'app.kubernetes.io/instance in (traccar,traccar-postgres)'

# 2.4 The two 6.16 behaviour changes still hit zero rows (expect 0 and 0).
#     A non-zero bad_uniqueid is a STOP: fix that device's identifier in the UI
#     first, or 6.16.0 throws "Invalid device identifier" while loading it.
kubectl -n $NS exec deploy/traccar-postgres -- psql -U traccar -d traccar -At \
  -c "select 'bad_uniqueid', count(*) from tc_devices where uniqueid ~ '[/\\\\]' or btrim(uniqueid) in ('','.','..');" \
  -c "select 'findhub_sender', count(*) from tc_devices where attributes like '%findHub%';"
# Negative control for the regex (must print 1 — proves the pattern CAN match a slash):
kubectl -n $NS exec deploy/traccar-postgres -- psql -U traccar -d traccar -At \
  -c "select count(*) from (values ('abc/def')) v(u) where u ~ '[/\\\\]';"

# 2.5 Longhorn backup of the DB volume is from last night (daily-backup-all-volumes @ 03:00)
kubectl -n storage get volume pvc-1cb9f072-fe84-469e-8a70-2abddd844e02 \
  -o jsonpath='{.status.robustness} lastBackupAt={.status.lastBackupAt}{"\n"}'
# expect robustness=healthy and a timestamp from today's 03:0x run
# (lastBackupAt can lag one cycle — docs/sops/backup.md "lastBackupAt Can Lag";
#  cross-check: kubectl -n storage get backups.longhorn.io -l backup-volume=pvc-1cb9f072-fe84-469e-8a70-2abddd844e02 --sort-by=.status.backupCreatedAt | tail -1)

# 2.6 Feeder alive: findmy-traccar-sync is up and uploading (non-zero "Upload status: 200" lines today)
launchctl list | grep com.mathiasuhl.findmy-traccar-sync       # PID column is a number, not "-"
grep -c "^\[$(date +%Y-%m-%d).*Upload status: 200" /Users/mu/code/findmy-traccar-sync/logs/stdout.log
```

Record the §4 baselines **immediately before** §3.3 (they are in §3.1).

## 3. Steps

### 3.1 Baselines (read-only)

```bash
NS=home-automation
kubectl -n $NS exec deploy/traccar-postgres -- psql -U traccar -d traccar -At \
  -c "select 'changelog', count(*) from databasechangelog;" \
  -c "select 'max_pos_id', max(id) from tc_positions;" \
  -c "select 'devices', count(*) from tc_devices;" \
  | tee /tmp/traccar-pre-6.16.txt
# 2026-09-27 values for orientation: changelog 61, max_pos_id ~265515, devices 21
ROLL_START=$(date +%Y-%m-%dT%H:%M:%S)      # local time, matches the sync log's timestamp prefix
echo "$ROLL_START" > /tmp/traccar-roll-start.txt
```

### 3.2 Logical dump — taken regardless of the "no migration" evidence

The dump is the floor under §5.3. Dump **inside the pod**, verify it there
(client matches server by construction), copy out with `kubectl cp` (never
`exec … cat >`, which truncated a dump on 2026-09-07), checksum both ends.

```bash
NS=home-automation
POD=$(kubectl -n $NS get pod -l app.kubernetes.io/instance=traccar-postgres -o jsonpath='{.items[0].metadata.name}')
mkdir -p ~/backups/traccar && chmod 0700 ~/backups/traccar
DUMP=~/backups/traccar/traccar-pre-6.16.0-$(date +%Y%m%d%H%M).dump

kubectl -n $NS exec "$POD" -- sh -c 'pg_dump -U traccar -d traccar --no-owner --no-privileges -Fc -f /tmp/traccar-pre-6.16.dump'
# Gate 1: the archive lists (a truncated/corrupt -Fc archive fails here)
kubectl -n $NS exec "$POD" -- sh -c 'pg_restore -l /tmp/traccar-pre-6.16.dump > /tmp/toc.txt' \
  || { echo "STOP: dump will not list — NOT a rollback. Do not run §3.3."; exit 1; }
# Gate 2: it contains the data we care about (expect >= 1 each)
kubectl -n $NS exec "$POD" -- sh -c "grep -c 'TABLE DATA public tc_positions' /tmp/toc.txt; grep -c 'TABLE DATA public databasechangelog ' /tmp/toc.txt"
# Copy out + checksum both ends (MUST match)
kubectl cp "$NS/$POD:/tmp/traccar-pre-6.16.dump" "$DUMP"
kubectl -n $NS exec "$POD" -- sha256sum /tmp/traccar-pre-6.16.dump; shasum -a 256 "$DUMP"
chmod 0600 "$DUMP"; ls -lh "$DUMP"     # DB is ~88 MB on disk; the -Fc dump is a fraction of that, never ~0
echo "$DUMP" > /tmp/traccar-dump-path.txt
```

Do not continue past this step on any ABORT or checksum mismatch.

### 3.3 Mark the update, bump the pin (GitOps)

```bash
cd /Users/mu/code/cberg-home-nextgen
runbooks/update-marker.sh add traccar home-automation 2 "traccar 6.15.3->6.16.0"

F=kubernetes/apps/home-automation/traccar/app/helmrelease.yaml
sed -i '' 's|tag: "6.15.3"|tag: "6.16.0@sha256:03ebb7ed2b219d4f25c326873bd022f5062f80bcae622a9d9422846b51951eda"|' "$F"
git diff -- "$F"
```

Dry-tested 2026-09-27 on a scratch copy (macOS BSD sed); the diff is exactly one line:

```
36c36
<               tag: "6.15.3"
---
>               tag: "6.16.0@sha256:03ebb7ed2b219d4f25c326873bd022f5062f80bcae622a9d9422846b51951eda"
```

No Alertmanager silence is needed: the Recreate outage is ~1-2 min, shorter
than every `for:` on the pod/deployment alerts and on the FindMy sync alerts
(`FindMyTraccarSyncFailing` needs >3 errors/h sustained 10 min). The
update-marker covers anything that slips through.

```bash
printf '%s\n' "feat(traccar): pin image 6.15.3 -> 6.16.0@sha256 (replaces floating 6.16)" "" \
  "Plan: runbooks/maintenance/plans/traccar-6.16.0.md. No schema changeset in 6.16.0." \
  "finding: F-36932ec1  security_ref: F-10584021" > /tmp/traccar-msg.txt
# append the session attribution lines to /tmp/traccar-msg.txt here
git commit --only "$F" -F /tmp/traccar-msg.txt
git log -1 --format=%s      # MUST be the subject above (shared-worktree message-swap guard)
git show --stat HEAD        # MUST list only helmrelease.yaml
git push
```

Flux picks it up via the webhook (Kustomization `traccar`, then
HelmRelease `traccar`). No manual `flux reconcile` unless §4.1 shows the HR
still on the old spec after 10 minutes.

## 4. Verification

### 4.1 Floor: rolled, running the pinned bytes, reporting the new version

```bash
NS=home-automation
kubectl -n $NS get helmrelease traccar -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.conditions[?(@.type=="Ready")].message}{"\n"}'
# imageID, NOT tag and NOT rollout status (rollout status green-lights the old generation):
kubectl -n $NS get pod -l app.kubernetes.io/instance=traccar -o jsonpath='{range .items[*]}{.metadata.name} {.status.containerStatuses[0].imageID} restarts={.status.containerStatuses[0].restartCount}{"\n"}{end}'
# PASS: exactly one pod, imageID ends in @sha256:03ebb7ed2b219d4f25c326873bd022f5062f80bcae622a9d9422846b51951eda, restarts=0
# FAIL shape: two lines (old pod still there), or ...@sha256:35346b4a... (still 6.15.3)

kubectl -n $NS port-forward svc/traccar-main 18082:8082 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s http://localhost:18082/api/server | python3 -c "import sys,json;v=json.load(sys.stdin).get('version');print(v);sys.exit(0 if v=='6.16.0' else 1)" && echo VERSION_OK || echo VERSION_FAIL
# Measured 2026-09-27 on 6.15.3: prints 6.15.3 -> VERSION_FAIL, i.e. this gate can fail.

# Presence gate FIRST (positive control for the reader): the new pod's log must
# contain Liquibase's no-op line exactly once. The wrapper tails
# logs/tracker-server.log, which lives on an emptyDir, so `kubectl logs` of the
# new pod holds exactly this pod's startup — no --since needed (a --since window
# would false-FAIL if §4.1 runs later than the window after start).
# Measured 2026-09-27 on the running 6.15.3 pod: 1.
kubectl -n $NS logs deploy/traccar | grep -c 'Database is up to date, no changesets to execute'
# PASS == 1. 0 = either the reader is blind (log wrapper/tail broken, wrong pod)
# or a changeset ran → FAIL this gate; then §4.2's changelog count DECIDES the
# rollback path (61 = git-revert still valid; != 61 = §5.3). A 0 here alone must
# NOT trigger a pg_restore: the wrapper's `sleep 3; tail -f` only surfaces the
# last 10 lines present at tail start, so an early Liquibase line can be missed.

# Absence gate, SAME reader: no 6.16 device-id failure, no Liquibase error
kubectl -n $NS logs deploy/traccar | grep -i -E 'invalid device identifier|liquibase.*(error|fail)|exception' | head -20
# PASS: no output — meaningful only because the presence gate above printed 1.
# (grep -i: upstream mixes case.)

# Record when the new pod went Ready — §4.3 filters failures from here:
READY_AT=$(date +%Y-%m-%dT%H:%M:%S); echo "$READY_AT" > /tmp/traccar-ready-at.txt
```

### 4.2 Contents: no schema migration happened (proves the rollback class)

**CONTENTS ASSERTION:** the Liquibase changelog is unchanged — measured by
`count(*) from databasechangelog`, compared to the §3.1 baseline (61 on
2026-09-27). Equal ⇒ 6.16.0 applied zero changesets, the DB is still exactly
what 6.15.3 expects, and §5.1 (git revert) is a complete rollback. Greater ⇒ a
changeset ran that the upstream `schema/` diff did not predict: STOP treating
this as git-revert; any rollback must use §5.3.

```bash
kubectl -n $NS exec deploy/traccar-postgres -- psql -U traccar -d traccar -At -c "select count(*) from databasechangelog;"
grep changelog /tmp/traccar-pre-6.16.txt
```

### 4.3 Contents: positions are still being ingested through osmand

**CONTENTS ASSERTION:** new positions land after the roll — measured by
`max(id) from tc_positions` compared to the §3.1 `max_pos_id` baseline; PASS
only when it is **strictly greater** AND the Mac-mini sync logged at least one
`Upload status: 200` after `ROLL_START` AND zero `upload failed` / non-200
lines after `READY_AT` (recorded at the end of §4.1; failures between
`ROLL_START` and `READY_AT` are the expected outage and are retried).

Use `id`, not `servertime`: `servertime` is stored as local Berlin time without
zone while the DB session is UTC, so a `now() - interval` window silently widens
by 2 h and would count pre-roll rows as post-roll (measured 2026-09-27: newest
servertime 12:02 at 10:06 UTC).

```bash
BASE=$(grep max_pos_id /tmp/traccar-pre-6.16.txt | cut -d'|' -f2)
ROLL_START=$(cat /tmp/traccar-roll-start.txt)
READY_AT=$(cat /tmp/traccar-ready-at.txt)
# Poll every 5 min (the sync runs every 300 s), up to 45 min:
kubectl -n $NS exec deploy/traccar-postgres -- psql -U traccar -d traccar -At \
  -c "select max(id), count(*) filter (where id > $BASE) from tc_positions;"
awk -v t="[$ROLL_START" '$0 >= t' /Users/mu/code/findmy-traccar-sync/logs/stdout.log | grep -c 'Upload status: 200'
awk -v t="[$READY_AT" '$0 >= t' /Users/mu/code/findmy-traccar-sync/logs/stdout.log | grep -i -E 'upload failed|Upload status: [^2]' | tail -5
# PASS: no output (after READY_AT).
```

Failure modes this catches: osmand listener not bound (uploads fail →
`upload failed (... Connection refused)`), osmand decoding broken (non-200
status), device lookup broken by the id validation (200 but no new row). Rate
reference for the wait: 3-16 positions/hour in the 14 h before this plan was
written, 4-12/h between 03:00 and 05:00. Upload failures during the ~2 min
outage are expected and **lossless**: the sync only stamps
`lastUploadedFixAt` on a 2xx, so a failed fix is re-sent next cycle
(`is_unchanged_fix`, findmy_json_traccar_bridge.py). If 45 min pass with no
changed fix at all (0 uploads, 0 failures — nobody moved), the result is
INCONCLUSIVE, not PASS: keep polling (the est_duration_min of 95 budgets up to
80 min for this section). If it is still INCONCLUSIVE at that point, the
extension spills out of the window: leave the plan `awaiting-soak`, hand the
§4.3 check to the next sweep, and do not mark it executed on 4.4 alone.

**§4.3 and §4.4 are the ONLY gates that prove the upgraded server ingests and
serves.** §4.5 is a feeder precondition, not an upgrade gate (see there).

### 4.4 osmand port and API login answer on the new build

```bash
# osmand handler is live: a param-less request returns 400 from Traccar.
# Measured 2026-09-27 on 6.15.3: 400. Dead listener / no endpoint prints 000.
curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 http://192.168.55.31:5055/

# Real login through the API with the admin credentials from traccar-secret,
# with a negative control. Measured 2026-09-27: good=200, bad=401, devices=21.
E=$(kubectl -n $NS get secret traccar-secret -o jsonpath='{.data.ADMIN_EMAIL}' | base64 -d)
P=$(kubectl -n $NS get secret traccar-secret -o jsonpath='{.data.ADMIN_PASSWORD}' | base64 -d)
curl -s -o /dev/null -w 'login-good %{http_code}\n' --data-urlencode "email=$E" --data-urlencode "password=$P" http://localhost:18082/api/session
BADPW=$(python3 -c 'import secrets;print(secrets.token_hex(12))')   # random wrong credential for the negative control
curl -s -o /dev/null -w 'login-bad %{http_code}\n'  --data-urlencode "email=$E" --data-urlencode "password=$BADPW" http://localhost:18082/api/session
curl -s -u "$E:$P" http://localhost:18082/api/devices | python3 -c "import sys,json;print('api_devices',len(json.load(sys.stdin)))"
# PASS: login-good 200, login-bad 401, api_devices == devices baseline (21)
unset E P BADPW
kill $PF 2>/dev/null
```

**CONTENTS ASSERTION:** every device survived the 6.16 identifier validation —
`api_devices` from `/api/devices` equals the §3.1 `devices` count (21 on
2026-09-27). A device whose id the new setter rejects most likely fails
`/api/devices` wholesale (the setter throws while the storage layer maps the
result rows, so the request errors instead of returning a short list) — the
python one-liner then raises instead of printing `api_devices`, which is a FAIL;
a short list is also a FAIL.

### 4.5 Feeder liveness — a PRECONDITION for §4.3, not an upgrade gate

These instruments cannot detect a broken Traccar on their own:
`findmy_json_traccar_bridge.py` catches per-device upload failures
(`upload failed (...)`, `requests.RequestException`) and the cycle still counts
as a success, so `findmy_sync_last_success_timestamp_seconds` advances and
`findmy_sync_errors_total` does not move while every upload is failing. What
they DO prove is that the feeder is alive and fetching from Apple — without
which §4.3's "no new rows" cannot be told apart from "nothing was sent". Check
them before trusting a §4.3 result (a FAIL here makes §4.3 INCONCLUSIVE, never
PASS).

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PPF=$!; sleep 3
for q in 'increase(findmy_sync_errors_total[30m])' 'time() - findmy_sync_last_success_timestamp_seconds' 'ALERTS{alertname="FindMyTraccarSyncFailing",alertstate="firing"}' 'ALERTS{alertname="FindMyTraccarSyncStale",alertstate="firing"}'; do
  echo "== $q"; curl -s --get http://localhost:19090/api/v1/query --data-urlencode "query=$q" \
  | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];[print(x['metric'].get('alertname',''),x['value'][1]) for x in r] or print('EMPTY')"
done
kill $PPF 2>/dev/null
```

CONTROL: metric findmy_sync_errors_total — a COUNTER of failed sync CYCLES (declared `("counter", "Total number of failed sync cycles.")` in the bridge; whole-cycle failures only, not per-device upload errors). Gate reads `increase(findmy_sync_errors_total[30m]) == 0` → feeder cycles are completing. EMPTY = the scrape (ScrapeConfig monitoring/findmy-traccar-sync, instance mac-mini) is broken → precondition FAIL, not a pass.
CONTROL: metric findmy_sync_last_success_timestamp_seconds — `time() - value` < 600 → the feeder completed a cycle in the last two intervals. Says nothing about whether its uploads were accepted.
CONTROL: alertname FindMyTraccarSyncFailing — not firing (feeder precondition).
CONTROL: alertname FindMyTraccarSyncStale — not firing (feeder precondition).

### 4.6 Close-out

```bash
runbooks/update-marker.sh clear traccar
kubectl -n home-automation exec deploy/traccar-postgres -- rm -f /tmp/traccar-pre-6.16.dump /tmp/toc.txt   # local copy in ~/backups/traccar stays
```

Keep `~/backups/traccar/traccar-pre-6.16.0-*.dump` for 7 days, then delete it.
In the executing commit, delete this plan file (plans are transient) and run
`runbooks/policy-cli.py finding close F-36932ec1 --commit <sha>`. Leave
F-10584021 to the next security sweep (partial remediation).

## 5. Rollback

### 5.1 Default (valid while §4.2 showed an unchanged changelog count)

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha-of-the-3.3-commit>
git log -1 --format=%s        # confirm it is the revert subject
git show --stat HEAD          # only helmrelease.yaml
git push
```

6.15.3 starts against a DB with the identical 61-changeset history, so
Liquibase is a no-op in that direction too.

### 5.2 Confirm the cluster is back

```bash
kubectl -n home-automation get pod -l app.kubernetes.io/instance=traccar -o jsonpath='{range .items[*]}{.status.containerStatuses[0].imageID}{"\n"}{end}'
# expect ...@sha256:35346b4af46d57adaeff69a548a7d2cb189a2487fe9c24c99044ee7aa104b5df (6.15.3), one pod
```

Then re-run §4.1 (expect `6.15.3` from `/api/server`), §4.3 and §4.4 against
the old build. If the HelmRelease is wedged `pending-upgrade`, follow
`application-update.md` §11 (`maxHistory: 1` means `helm rollback` cannot reach
the old revision — the git revert is the path).

### 5.3 Only if §4.2 showed the changelog count CHANGED (unexpected migration)

A changeset ran; 6.15.3 may refuse or mis-read the migrated schema. Restore the
§3.2 dump **after** the revert has Traccar back on 6.15.3 but **before** it
takes writes — so stop Traccar first:

```bash
NS=home-automation
DUMP=$(cat /tmp/traccar-dump-path.txt)
# 1. Revert per 5.1, AND in the same commit scale traccar to 0 by setting
#    `controllers.main.replicas: 0` in helmrelease.yaml; push; wait until no traccar pod exists.
# 2. Restore into the existing database (single DB; roles unchanged, --no-owner dump):
POD=$(kubectl -n $NS get pod -l app.kubernetes.io/instance=traccar-postgres -o jsonpath='{.items[0].metadata.name}')
kubectl cp "$DUMP" "$NS/$POD:/tmp/restore.dump"
kubectl -n $NS exec "$POD" -- sha256sum /tmp/restore.dump; shasum -a 256 "$DUMP"     # MUST match
kubectl -n $NS exec "$POD" -- pg_restore -U traccar -d traccar --clean --if-exists --no-owner --no-privileges /tmp/restore.dump
kubectl -n $NS exec "$POD" -- psql -U traccar -d traccar -At -c "select count(*) from databasechangelog;" -c "select max(id) from tc_positions;"
# expect changelog == the §3.1 baseline (61) and max(id) == the §3.1 max_pos_id
# 3. Remove the replicas: 0 line, commit, push; re-run §4.1-4.4 against 6.15.3.
# 4. Re-feed the positions lost between dump and restore: the sync believes Traccar
#    already has them. Per its own docstring, delete `lastUploadedFixAt` from each
#    entry in /Users/mu/code/findmy-traccar-sync/data/findmy-resume.json (daemon
#    stopped: launchctl unload/load ~/Library/LaunchAgents/com.mathiasuhl.findmy-traccar-sync.plist)
#    so the latest fix per device is re-sent. Intermediate fixes in that gap are lost.
```

Slower alternative for the same case: restore the Longhorn backup of
`pvc-1cb9f072-fe84-469e-8a70-2abddd844e02` from the 03:0x run
(`docs/sops/backup.md`), which loses everything since that backup.

## 6. Interference notes

- **Outage:** Recreate strategy → ~1-2 min with no traccar pod: the public
  hostname on `envoy-external` returns 503 for that span and
  192.168.55.31:5055 refuses connections. The Gateway and HTTPRoute are not
  modified, so no other app on `envoy-external` is affected — hence
  `shared: []`.
- **Mac-mini feeder:** findmy-traccar-sync runs every 300 s; one cycle may log
  `upload failed`, and it retries those fixes next cycle (lossless). It must be
  running for §4.3 — if the Mac mini itself is being worked on in the same
  window, run this plan before or after, not during.
- **conflicts_with:** `flux-reconciler-impersonation` (exclusive; changes how
  Flux applies in this namespace), `flux-oci-chart-sources` (repoints the
  bjw-s chart source this HelmRelease renders from), `helm-drift-detection`
  (writes a new field into `helmrelease/traccar`), `kube-prometheus-stack-91.4.1`
  (§4.5 reads Prometheus), `chart-patches-coredns-reloader-blackbox` (rolls
  CoreDNS, which the JDBC connect to `traccar-postgres` resolves through at
  startup), `app-template-5.2.1` (its Batch A seds the chart version into
  this same `helmrelease.yaml` — two writers, one file; run them in separate
  windows and re-run this plan's `manifest-pin-still-6.15.3` premise after it).
  Reciprocity: `flux-reconciler-impersonation`, `flux-oci-chart-sources`,
  `helm-drift-detection`, `kube-prometheus-stack-91.4.1` and
  `app-template-5.2.1` do not list `traccar-6.16.0` back yet; `--validate`
  does not check reciprocity — add it on their side when next edited.
- `n8n-2.39.8` / `n8n-chart-2.1.1` share the namespace only; no shared object,
  no conflict.
- The app-template 5.1.0 → 5.2.1 chart bumps for `traccar` and
  `traccar-postgres` (F-ecd3db25, F-159c75df) are deliberately out of scope;
  do not batch them into this commit — a chart and an image change in one
  reconcile make a failure unattributable.
- No node reboot, no PVC change, no secret change.
