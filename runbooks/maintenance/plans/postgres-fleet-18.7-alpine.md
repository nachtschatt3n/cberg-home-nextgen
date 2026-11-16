---
plan_id: postgres-fleet-18.7-alpine
component: postgres                    # coverage group postgres-fleet-18.7-alpine (image-fleet, 2 members, both CronJobs in kube-system)
pr: 504                                # Renovate #504 "update postgres ( 18.6 -> 18.7 )" carries these two hunks AND nine other files
                                       # (stateful databases). This plan delivers ONLY its two CronJob hunks by direct edit; #504 is NOT merged.
kind: image
current: "18.6-alpine"                 # postgres:18.6-alpine@sha256:d3e1620b... on cronjob/authentik-channels-cleanup and cronjob/authentik-db-probe
target: "18.7-alpine"                  # postgres:18.7-alpine@sha256:75dcac3d... (multi-arch index; amd64 child fa1b61f5...)
update_type: minor                     # semver token 18.6 -> 18.7 (Renovate label type/minor). In PostgreSQL terms a bug-fix release of major 18.
risk: low                              # two psql-client CronJobs; no server, no volume, no long-running pod, no schema; revert is complete
est_duration_min: 15                   # pre-checks 3 | edit+commit+push 2 | reconcile 3 | two manual Job runs + scrape wait 5 | close-out 2
needs_reboot: false
touches:
  namespaces: [kube-system]
  resources:
    - cronjob/kube-system/authentik-channels-cleanup   # image only; next Job picks it up
    - cronjob/kube-system/authentik-db-probe           # image only; next Job picks it up
    - kustomization/kube-system/authentik              # the Flux Kustomization that applies both files (nothing else in it changes)
    # CLIENT surfaces, read or written by the two Jobs, not edited:
    - deployment/kube-system/authentik-pg              # the server both Jobs connect to (postgres:18.6-bookworm, stays put)
    - service/monitoring/prometheus-pushgateway        # authentik-db-probe pushes its five gauges here
  shared:
    - monitoring                       # section 4 reads Prometheus, and the probe feeds the AuthentikAudit* alert inputs
    - authentik-db                     # both Jobs are clients of the live Authentik database; channels-cleanup writes to it
depends_on:
  - postgres-fleet-18.7-bookworm       # bookworm FIRST: authentik-db-probe is one of its instruments (its 6.2); pre-check 2.7 enforces it at window time
conflicts_with:
  - postgres-digest-refresh-2026-11    # vetted, sun-attended:2026-12-20 - its stage 1 seds the SAME two image lines (d3e1620 -> 18.6 digest refresh). See section 6.
  - kube-prometheus-stack-93.3.0      # draft, exclusive, window null: restarts Prometheus, which this plan's gates read (retargeted 2026-11-16 from retired 92.22.0)
  - talos-linux-1.14.5                 # node roll moves authentik-pg; the probe Job in section 4 would fail for an unrelated reason
  - longhorn-1.13.0                    # engine work under authentik-pg's volume; same confound
  - flux-reconciler-impersonation      # blocked - changes who applies the kube-system/authentik Kustomization this plan relies on
  - flux-oci-chart-sources             # vetted, sun-attended:2026-12-13 - reworks sources reconciled in kube-system the same night
exclusive: false
security_ref: F-5988252e               # citation only: the AR-112-accepted register row for this image tag; this bump is its remedy for 2 of its consumers. Detail is DB-only. Do NOT close it from this plan (section 4.6).
capability_change: false               # same PostgreSQL major, client-only use (psql + busybox sh/wget); no feature, route, permission or exposure change
rollback_class: git-revert             # nothing forward-only: no server binary, no data directory, no migration. The old digest is still pullable.
finding_refs: [F-e0cef03a, F-87b5a6a0]  # version rows opened 2026-11-14 (PLAN lane, held by *authentik*): authentik-db-probe and authentik-channels-cleanup 18.6-alpine -> 18.7-alpine. Closed in 4.6.
review: ready-for-go@2026-11-16
status: vetted
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/authentik.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-11-13"
premises:
  - id: cronjobs-on-current-image
    why: Both CronJobs still carry the 18.6-alpine pin this plan replaces. Fails if the digest-refresh plan or a merge of PR 504 got there first.
    run: kubectl get cronjob authentik-channels-cleanup authentik-db-probe -n kube-system -o jsonpath='{.items[*].spec.jobTemplate.spec.template.spec.containers[0].image}'
    expect_exact: "postgres:18.6-alpine@sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2 postgres:18.6-alpine@sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2"
  - id: main-probe-still-old-pin
    why: The sed in section 3 matches this exact string; a different pin on main makes it a silent no-op.
    run: git show origin/main:kubernetes/apps/kube-system/authentik/app/cronjob-db-probe.yaml | grep -c 'postgres:18.6-alpine@sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2'
    expect_exact: "1"
  - id: main-cleanup-still-old-pin
    why: Same, for the second file.
    run: git show origin/main:kubernetes/apps/kube-system/authentik/app/cronjob-channels-cleanup.yaml | grep -c 'postgres:18.6-alpine@sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2'
    expect_exact: "1"
  - id: authentik-pg-ready
    why: Section 4 runs a real probe against authentik-pg. If the server is down or mid-restart (sibling bookworm plan, node roll) the gate would fail for a reason that is not this change.
    run: kubectl get deploy authentik-pg -n kube-system -o jsonpath='{.status.readyReplicas}'
    expect_exact: "1"
  - id: server-is-major-18
    why: The 18.7 psql client is only planned against a major-18 server. Kept major-wide on purpose - plan-premises.py does not read depends_on, so an 18.7-only premise would fail every sweep until bookworm runs. The bookworm-first ORDER is checked at window time by pre-check 2.7.
    run: kubectl get deploy authentik-pg -n kube-system -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_matches: '^postgres:18\.\d+-bookworm'
  - id: cronjobs-not-suspended
    why: A suspended CronJob would make the scheduled-run evidence in section 2 meaningless.
    run: kubectl get cronjob authentik-channels-cleanup authentik-db-probe -n kube-system -o jsonpath='{.items[*].spec.suspend}'
    expect_exact: "false false"
  - id: pushgateway-service-present
    why: The probe pushes to prometheus-pushgateway.monitoring port 9091; the contents gate in section 4 reads what it pushed.
    run: kubectl get svc prometheus-pushgateway -n monitoring -o jsonpath='{.spec.ports[0].port}'
    expect_exact: "9091"
  - id: authentik-kustomization-ready
    why: The change is delivered by the kube-system/authentik Flux Kustomization; it must be healthy before a commit lands in it.
    run: kubectl get kustomization authentik -n kube-system -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: no-leftover-verification-jobs
    why: Section 4 creates Jobs named pg187-*; a leftover from an aborted run would be mistaken for this run's evidence.
    run: kubectl get jobs -n kube-system -o name | grep -c pg187-
    expect_exact: "0"
---

# postgres 18.6-alpine -> 18.7-alpine on the two Authentik helper CronJobs

## 1. Summary & why held

**What changes.** One image line in each of two files:

| CronJob (ns kube-system) | File | Uses the image for |
|---|---|---|
| `authentik-channels-cleanup` (every 6h) | `kubernetes/apps/kube-system/authentik/app/cronjob-channels-cleanup.yaml` | `psql` + POSIX `sh`: deletes expired `django_channels_postgres_message` rows, `VACUUM`s that table |
| `authentik-db-probe` (hourly, `:17`) | `kubernetes/apps/kube-system/authentik/app/cronjob-db-probe.yaml` | `psql` + busybox `wget --post-file`: pushes five gauges to the Pushgateway |

`postgres:18.6-alpine@sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2`
becomes
`postgres:18.7-alpine@sha256:75dcac3dfb1cd01ca3536910bbc84128759362f8b118bf8c55b38a94f68f3b73`.

Neither CronJob runs a PostgreSQL **server**. The server (`deployment/authentik-pg`, `postgres:18.6-bookworm`) is not touched here; it
belongs to the sibling plan `postgres-fleet-18.7-bookworm`, which runs first (`depends_on`, section 6).

**Which PR covers it.** Renovate **#504** (`renovate/postgres-18.x`, head `962bde24`, CI green) carries exactly these two hunks with the
same target digest, but it also edits nine other files: `authentik-pg`, `mealie-pg`, `superset-pg18`, `paperclip-postgresql`,
`teslamate`/`traccar`/`penpot-db` postgres HelmReleases, `sweep-heartbeat` and `media-library-audit`. Merging #504 would restart seven
databases. **This plan does not merge #504**; it applies the two hunks by direct edit and Renovate rebases the PR. #227 (the `18.6-alpine`
digest refresh) also touches these two lines and is owned by `postgres-digest-refresh-2026-11` (section 6).

**Why it is held, and what that hold is worth.** `coverage.py` routes both members to PLAN with the `*authentik*` deny rule's reason
(`runbooks/auto-update-policy.yaml`, HELD 2026-09-22). The glob matches the **component names** `authentik-channels-cleanup` and
`authentik-db-probe`. The rule's two stated hazards are (a) the Authentik *chart* reached the unattended lane with unreadable release
notes, and (b) the chart and the two `patch-session-settings` initContainer pins of `ghcr.io/goauthentik/server` can drift apart. Neither
describes these images: the image repo is `postgres`, no Authentik chart or server image moves, and the release notes were readable (below).
On the rule's own terms this is a name-match false positive, the same shape as the `*affine*` glob that was narrowed on 2026-09-26. The
plan is still written; whether the glob should be narrowed is an operator call, not this plan's.

**The real, smaller hazard (why this is `low`, not "trivial").** The probe's failure mode is quiet: by design it pushes nothing on
failure, and `AuthentikAuditFreshnessProbeStale` only fires after 6h + 30m (`authentik-alerts.yaml`, `expr: time() - max(...) > 60*60*6`,
`for: 30m`). An image whose `psql` or `wget` broke would go unnoticed until mid-morning. Section 4 therefore runs one real probe and reads
what it pushed.

**Upstream evidence** (PostgreSQL 18.7 release notes, release date 2026-11-12, `https://www.postgresql.org/docs/release/18.7/`):

> A dump/restore is not required for those running 18.X. However, several different bugs have been discovered that could result in index
> corruption. Examine the changelog entries below that mention REINDEX ... Also, existing incremental backup files should not be trusted ...

Those migration notes are **server-side** (REINDEX, incremental backups, the new `composite_type_mismatch` parameter, C-extension
rebuilds) and belong to the bookworm sibling plan. The client-side entries are bug fixes only: psql `COPY FROM STDIN` counting in
multi-query strings, `\getresults` argument handling, out-of-memory handling in backslash commands, small memory leaks, a libpq GSS leak.
The two scripts use `psql -c` / `-t` / `-At -F' '` / `-v ON_ERROR_STOP=1` with plain `SELECT`/`DELETE`/`TRUNCATE`/`VACUUM`; none of the
changed code paths is used. An 18.7 `psql` against an 18.6 server (and later 18.6-era habits against an 18.7 server) is same-major and
supported in either order.

**Image contents, measured from the registry 2026-11-13** (config blob + base layer of the amd64 child of each index):

| | old `d3e1620b...` (child `63bdc97d...`) | new `75dcac3d...` (child `fa1b61f5...`) |
|---|---|---|
| built | 2026-08-13 | 2026-11-12 |
| `PG_VERSION` | 18.6 | 18.7 |
| Alpine | 3.24.1 | 3.24.4 |
| BusyBox | v1.37.0, `--post-file` present | v1.37.0, `--post-file` present |

`18.7-alpine` and `18.7-alpine3.24` are the same index digest. Same Alpine line and same BusyBox, so the probe's `wget --post-file`
dependency (the manifest comment calls it out) is unchanged.

## 2. Pre-checks

Run from the repo root on the Mac mini (zsh). Stop on any FAIL.

**Shell state does not persist between tool calls.** Every value a later block needs (`W`, `SHA`, `T0`, `J`, `J2`) is appended to
the fixed state file `/tmp/maint-postgres-fleet-18.7-alpine/state` as `KEY=value` lines, and every later block (sections 3, 4 and 5)
starts by re-reading it. Create it once, here:

```bash
# 2.0 state file (fixed path; a leftover from an earlier attempt is archived, not reused)
S=/tmp/maint-postgres-fleet-18.7-alpine
[ -d "$S" ] && mv "$S" "$S.$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$S" && printf 'W=%s\n' "$S" > "$S/state" && cat "$S/state"     # PASS: W=/tmp/maint-postgres-fleet-18.7-alpine
```

```bash
# 2.1 premises (the run-time gate)
.venv/bin/python3 runbooks/plan-premises.py postgres-fleet-18.7-alpine --require-premises     # PASS, no REFUSED line

# 2.2 the target tag still resolves to the planned index digest (a rebuilt tag means: STOP, re-plan the digest)
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/postgres:pull" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -sI -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.oci.image.index.v1+json" https://registry-1.docker.io/v2/library/postgres/manifests/18.7-alpine | grep -i docker-content-digest
# PASS: docker-content-digest: sha256:75dcac3dfb1cd01ca3536910bbc84128759362f8b118bf8c55b38a94f68f3b73
# If the digest differs the tag was rebuilt. That is not a fault: the pinned digest stays pullable. Continue with the PLANNED digest
# only if the next command returns 200; otherwise STOP.
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.oci.image.index.v1+json" https://registry-1.docker.io/v2/library/postgres/manifests/sha256:75dcac3dfb1cd01ca3536910bbc84128759362f8b118bf8c55b38a94f68f3b73
# PASS: 200

# 2.3 the rollback target is still pullable by digest (verified 200 on 2026-11-13)
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.oci.image.index.v1+json" https://registry-1.docker.io/v2/library/postgres/manifests/sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2
# PASS: 200

# 2.4 both CronJobs are healthy BEFORE the change (so a later failure is attributable)
kubectl get cronjob authentik-channels-cleanup authentik-db-probe -n kube-system -o custom-columns='NAME:.metadata.name,LAST:.status.lastScheduleTime,LASTOK:.status.lastSuccessfulTime'
# PASS: for each row LASTOK is within seconds after LAST (measured 2026-11-13: 02:17:00Z / 02:17:04Z and 00:00:00Z / 00:00:07Z).
# FAIL (LASTOK older than LAST, or <none>): the job is already failing on the OLD image. STOP, that is a separate fault.

# 2.5 no scheduled run is about to collide with the manual runs in section 4
date -u +%H:%M     # avoid starting section 4 at minute 15-18 (probe tick :17) or at 05:58-06:02 / 11:58-12:02 / 17:58-18:02 / 23:58-00:02 UTC
kubectl get cronjob authentik-channels-cleanup authentik-db-probe -n kube-system -o jsonpath='{.items[*].status.active}'
# PASS: prints nothing (no active Job)

# 2.6 working tree: the two files are clean and main is current
git fetch origin
git status --short kubernetes/apps/kube-system/authentik/app/cronjob-channels-cleanup.yaml kubernetes/apps/kube-system/authentik/app/cronjob-db-probe.yaml   # PASS: no output
git rev-list --count HEAD..origin/main    # PASS: 0 (otherwise `git pull --rebase` first)

# 2.7 depends_on is met: postgres-fleet-18.7-bookworm has run and stuck (authentik-pg serves 18.7)
kubectl get deploy authentik-pg -n kube-system -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}' | grep -c '^postgres:18\.7-bookworm'
# PASS: 1.  FAIL: 0 - authentik-pg is still (or again, after a bookworm rollback) on 18.6-bookworm. STOP: bookworm goes first.
# Measured 2026-11-16 (before bookworm ran): prints 0, image postgres:18.6-bookworm - so this check can fail.
```

## 3. Steps

GitOps only. No manual `flux reconcile`; the push webhook reconciles `kube-system/authentik`.

```bash
cd /Users/mu/code/cberg-home-nextgen
. /tmp/maint-postgres-fleet-18.7-alpine/state && [ -n "$W" ] || echo 'FAIL: no state file - run 2.0 first'
OLD='postgres:18.6-alpine@sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2'
NEW='postgres:18.7-alpine@sha256:75dcac3dfb1cd01ca3536910bbc84128759362f8b118bf8c55b38a94f68f3b73'

# 3.1 edit (dry-tested on scratch copies on macOS 2026-11-13; BSD sed, `|` delimiter, no regex classes)
sed -i '' "s|image: $OLD|image: $NEW|" kubernetes/apps/kube-system/authentik/app/cronjob-channels-cleanup.yaml
sed -i '' "s|image: $OLD|image: $NEW|" kubernetes/apps/kube-system/authentik/app/cronjob-db-probe.yaml

# 3.2 gate the commit on the diff: exactly two added image lines, nothing else
git diff -U0 -- kubernetes/apps/kube-system/authentik/app/ | grep -c "^+ *image: $NEW"      # PASS: 2   (0 or 1 = the sed did not match: STOP)
git diff --numstat -- kubernetes/apps/kube-system/authentik/app/ | wc -l                    # PASS: 2 files
git diff --shortstat -- kubernetes/apps/kube-system/authentik/app/                          # PASS: 2 files changed, 2 insertions(+), 2 deletions(-)
```

Expected diff (from the dry test), line 32 of `cronjob-channels-cleanup.yaml` and line 64 of `cronjob-db-probe.yaml`:

```
-              image: postgres:18.6-alpine@sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2
+              image: postgres:18.7-alpine@sha256:75dcac3dfb1cd01ca3536910bbc84128759362f8b118bf8c55b38a94f68f3b73
```

The comments above both image lines say "verified against the registry 2026-08-18"; leave them, or update the date in the same commit
(then the shortstat gate reads `4 insertions(+), 4 deletions(-)`; do not do both halves in separate commits).

```bash
# 3.3 commit exactly these two paths (shared worktree: --only, then verify the subject is yours)
cd /Users/mu/code/cberg-home-nextgen
. /tmp/maint-postgres-fleet-18.7-alpine/state && [ -n "$W" ] || echo 'FAIL: no state file - run 2.0 first'
printf 'chore(container): update postgres 18.6-alpine -> 18.7-alpine on the two authentik helper CronJobs\n\nClient-only use (psql + busybox wget); authentik-pg server untouched. Two hunks of Renovate #504, delivered by maintenance plan postgres-fleet-18.7-alpine.\n' > "$W/msg.txt"
git commit --only kubernetes/apps/kube-system/authentik/app/cronjob-channels-cleanup.yaml kubernetes/apps/kube-system/authentik/app/cronjob-db-probe.yaml -F "$W/msg.txt"
git log -1 --format=%s          # PASS: the subject above. Anything else: amend before pushing.
git show --stat HEAD            # PASS: exactly the two files
printf 'SHA=%s\n' "$(git rev-parse HEAD)" >> "$W/state"; grep '^SHA=' "$W/state"     # PASS: SHA=<40 hex>, the commit just verified
git push origin main
```

Add the attribution trailer the session requires to `msg.txt` before committing. Do not put any vulnerability detail in the message.

## 4. Verification

```
CONTENTS ASSERTION: a Job running the NEW image reached the live Authentik database with psql and delivered its result - measured by
  authentik_db_probe_last_success_timestamp_seconds in Prometheus, which must be >= T0 (a unix time taken before the manual run), and by
  authentik_audit_event_rows > 0 from the same push. Baseline 2026-11-13: with no new run the same comparison prints STALE (4.3).
CONTROL: metric authentik_db_probe_last_success_timestamp_seconds - written only by a probe run that got through psql AND wget; gate: value >= T0
CONTROL: metric authentik_audit_event_rows - pushed in the same group; gate: > 0 (an empty table or the wrong database reads 0)
CONTROL: alertname AuthentikAuditFreshnessProbeStale - asserted not firing before and after. It CANNOT fire inside the window (6h + 30m), so it is a baseline, not the gate.
CONTROL: alertname AuthentikAuditFreshnessProbeMissing - asserted not firing after (fires when the pushed series are absent)
```

**4.1 Flux applied the commit and both CronJobs carry the new pin** (poll up to 5 min):

```bash
. /tmp/maint-postgres-fleet-18.7-alpine/state && echo "$SHA"   # the commit from 3.3
flux get kustomization authentik -n kube-system          # PASS: READY True, revision main@sha1:<first 7+ chars of $SHA>
kubectl get cronjob authentik-channels-cleanup authentik-db-probe -n kube-system -o jsonpath='{.items[*].spec.jobTemplate.spec.template.spec.containers[0].image}' | tr ' ' '\n' | grep -c 'postgres:18.7-alpine@sha256:75dcac3dfb1cd01ca3536910bbc84128759362f8b118bf8c55b38a94f68f3b73'
# PASS: 2.  FAIL prints 0 (not reconciled yet: the output still shows 18.6-alpine@d3e1620b) or 1 (one file missed).
```

**4.2 One real probe run on the new image.** This is the single imperative action in the plan: a transient Job created from the
CronJob's own template (same pattern as the vetted `postgres-digest-refresh-2026-11` section 4). It is read-only against the database
and pushes the same group the hourly run pushes.

```bash
. /tmp/maint-postgres-fleet-18.7-alpine/state && [ -n "$W" ] || echo 'FAIL: no state file'
T0=$(date -u +%s); J=pg187-probe-$(date -u +%H%M%S)
printf 'T0=%s\nJ=%s\n' "$T0" "$J" >> "$W/state"
kubectl create job --from=cronjob/authentik-db-probe "$J" -n kube-system
kubectl wait --for=condition=complete "job/$J" -n kube-system --timeout=180s
# PASS: job.batch/pg187-probe-... condition met
# FAIL: "error: timed out waiting for the condition". Read why:
#   kubectl get pod -n kube-system -l "job-name=$J" -o wide     (ImagePullBackOff / ErrImagePull = the digest cannot be pulled)
#   kubectl logs "job/$J" -n kube-system                        ("FATAL: query against authentik-pg failed" = psql; a bare wget error = the push)
# The script runs under `set -eu`, so a psql OR a wget failure exits non-zero and the Job never completes.

kubectl logs "job/$J" -n kube-system | grep -c 'pushed to pushgateway job=authentik-db-probe'      # PASS: 1.  FAIL: 0
kubectl logs "job/$J" -n kube-system | grep -c '^host=authentik-pg '                                # PASS: 1 (it queried the LIVE database, not the frozen rollback)

kubectl get pod -n kube-system -l "job-name=$J" -o jsonpath='{.items[0].status.containerStatuses[0].imageID}' | grep -c -e 75dcac3dfb1cd01ca3536910bbc84128759362f8b118bf8c55b38a94f68f3b73 -e fa1b61f5a4844f4d4b73c9b15716cfc75fe70c931f2d32723630f3b900056366
# PASS: 1.  FAIL: 0 (the pod ran some other image; print the jsonpath without the grep to see which).
# Both digests are accepted on purpose: containerd reports either the index or the platform child. Measured 2026-11-13 on the OLD
# pin: spec says index d3e1620b..., the pod's imageID says child 63bdc97d... (all three nodes are amd64; fa1b61f5... is the amd64
# child of 75dcac3d...). A gate that expected only the index digest would fail on a correct rollout.
```

**4.3 The contents gate: what the probe pushed arrived in Prometheus.** Pushgateway is scraped every 30s (measured), so poll for up to
2 minutes.

```bash
. /tmp/maint-postgres-fleet-18.7-alpine/state && [ -n "$T0" ] || echo 'FAIL: T0 missing - re-run 4.2'
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
for i in 1 2 3 4 5 6 7 8; do
  R=$(curl -s --data-urlencode 'query=authentik_db_probe_last_success_timestamp_seconds' http://localhost:19090/api/v1/query | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; t0=int(sys.argv[1]); print('NO_SERIES' if not r else ('FRESH ' if float(r[0]['value'][1])>=t0 else 'STALE ')+r[0]['value'][1])" "$T0")
  echo "$R"; case "$R" in FRESH*) break;; esac; sleep 15
done
# PASS: a line starting with FRESH.
# FAIL: STALE <old timestamp> after all 8 polls (the run pushed nothing), or NO_SERIES (the scrape or the metric is gone).
# Negative controls, measured 2026-11-13 with this exact pipeline: T0=now with no new run -> "STALE 1794536221";
# a nonexistent metric name -> "NO_SERIES". So the gate can fail both ways it needs to.

curl -s --data-urlencode 'query=authentik_audit_event_rows' http://localhost:19090/api/v1/query | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print('NO_SERIES' if not r else ('ROWS_OK' if float(r[0]['value'][1])>0 else 'ROWS_ZERO'))"
# PASS: ROWS_OK.  FAIL: ROWS_ZERO or NO_SERIES.   (the row count itself is not printed on purpose)

# Alert check. `count(...) or vector(0)` prints 0 for a firing-free rule AND for a rule that is not loaded or an ALERTS series that
# is not there at all, so on its own it is an ABSENCE reading that cannot fail. It is made able to fail by two controls run first,
# with the same query shape:
for q in 'count(ALERTS{alertname="Watchdog",alertstate="firing"}) or vector(0)' 'count(ALERTS{alertname=~"AuthentikAuditFreshnessProbeStale|AuthentikAuditFreshnessProbeMissing",alertstate="firing"}) or vector(0)'; do
  curl -s --data-urlencode "query=$q" http://localhost:19090/api/v1/query | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['result'][0]['value'][1])"
done
# PASS: first line 1 (POSITIVE CONTROL: Watchdog always fires, so this query shape does see a firing alert; 0 here means ALERTS
#       is not being read and the second line is meaningless - STOP), second line 0.
# Measured 2026-11-16: "1" / "0"; a nonexistent alertname in the same shape also prints 0, which is why the controls are required.
curl -s http://localhost:19090/api/v1/rules | python3 -c "import sys,json; g=json.load(sys.stdin)['data']['groups']; print(len([r for x in g for r in x['rules'] if r['name'] in ('AuthentikAuditFreshnessProbeStale','AuthentikAuditFreshnessProbeMissing')]))"
# PASS: 2 (both rules are loaded, so their 0 means "not firing", not "not evaluated"). Measured 2026-11-16: 2.
# This alert check is CORROBORATING, not the contents gate: Stale cannot fire inside the window (6h + 30m). FRESH + ROWS_OK above decide.
kill $PF 2>/dev/null
```

**4.4 One real cleanup run on the new image.** Same Job the cluster runs every 6h; it deletes only already-expired channel messages
and is idempotent. Skip-proof because `set -e` makes any psql error fail the Job.

```bash
. /tmp/maint-postgres-fleet-18.7-alpine/state && [ -n "$W" ] || echo 'FAIL: no state file'
J2=pg187-cleanup-$(date -u +%H%M%S); printf 'J2=%s\n' "$J2" >> "$W/state"
kubectl create job --from=cronjob/authentik-channels-cleanup "$J2" -n kube-system
kubectl wait --for=condition=complete "job/$J2" -n kube-system --timeout=300s      # PASS: condition met.  FAIL: timed out (see pod + logs as in 4.2)
kubectl logs "job/$J2" -n kube-system | grep -c -i -e 'No expired messages to clean up' -e 'Cleanup complete!'
# PASS: 1 (measured on the old image 2026-11-13: "Found 0 expired messages" / "No expired messages to clean up").
# FAIL: 0 - the script ended some other way; read the full log.
```

**4.5 Close-out.**

```bash
. /tmp/maint-postgres-fleet-18.7-alpine/state && echo "J=$J J2=$J2"     # both names must be non-empty
kubectl delete job "$J" "$J2" -n kube-system
kubectl get jobs -n kube-system -o name | grep -c pg187-          # PASS: 0
```

**4.6 Close the two version findings, IF they are still open** (only after 4.1-4.5 all passed; agent-authored closes never happen on their own, but the sweep can auto-close a row first once it stops seeing the old tag, so this step must skip cleanly when a row is already resolved or absent):

```bash
cd /Users/mu/code/cberg-home-nextgen
. /tmp/maint-postgres-fleet-18.7-alpine/state && [ -n "$SHA" ] || echo 'FAIL: SHA missing'
source runbooks/lib/sweep-pg-dsn.sh && sweep_pg_dsn_up || echo 'FAIL: no DSN - do not read a refusal as a verdict'
for f in F-e0cef03a F-87b5a6a0; do
  OUT=$(.venv/bin/python3 runbooks/policy-cli.py finding show $f 2>&1)
  ST=$(printf '%s\n' "$OUT" | grep -E '^ *status ' | awk '{print $2}')
  case "$f" in F-e0cef03a) R='authentik-db-probe on postgres 18.7-alpine; manual probe Job FRESH in Prometheus (plan postgres-fleet-18.7-alpine 4.3)';; *) R='authentik-channels-cleanup on postgres 18.7-alpine; manual cleanup Job completed (plan postgres-fleet-18.7-alpine 4.4)';; esac
  if [ -z "$ST" ]; then
    case "$OUT" in *"not found"*) echo "SKIP $f: row absent (nothing to close)";; *) echo "FAIL $f: finding show errored (DB/DSN), not a verdict - stop and fix before reading anything";; esac
  elif [ "$ST" = resolved ]; then echo "SKIP $f: already resolved by the sweep"
  else .venv/bin/python3 runbooks/policy-cli.py finding close $f --commit "$SHA" --reason "$R"; fi
done
for f in F-e0cef03a F-87b5a6a0; do .venv/bin/python3 runbooks/policy-cli.py finding show $f | grep -E '^ *(status|resolved_commit) '; done
# PASS: per finding either a SKIP line (absent / already resolved) or a 'closed F-...' line, and afterwards status = resolved (or a literal 'not found' for the row). A 'FAIL ... show errored' line means the DB was unreachable: it is NOT a pass.
# FAIL prints: 'FAIL: no DSN', or a finding still reading status unchanged after the loop. A SKIP is a PASS, never a reason to stop the window.
# Open on 2026-11-16 (status 'unchanged'), so the close path is the expected one today; the skip branches cover a sweep that ran first.
sweep_pg_dsn_down
```

**Not closed here: `security_ref` F-5988252e** (the AR-112-accepted register row for the `18.6-alpine` tag). This plan moves 2 of that
tag's consumers off it; `superset-pg18`, `paperclip-postgresql`, `sweep-heartbeat` and `media-library-audit` stay on `18.6-alpine`, so
the row is still true after this plan. It resolves on its own when the security sweep stops seeing the tag. Note for the AR owner: AR-112's
needle is `postgres:18.` and therefore also matches `18.7-alpine` - it does not lapse with this bump.

Deferred, non-blocking (report it, do not wait in the window): the next scheduled `:17` probe tick completes
(`kubectl get cronjob authentik-db-probe -n kube-system -o jsonpath='{.status.lastSuccessfulTime}'` moves past the window start).

## 5. Rollback

Nothing forward-only happens: no server binary, no volume, no schema, no migration. The cleanup run only removes rows that the old image
would have removed on its next tick. So the revert is complete.

```bash
cd /Users/mu/code/cberg-home-nextgen
. /tmp/maint-postgres-fleet-18.7-alpine/state; echo "SHA=$SHA"
# If SHA is empty (state file lost), recover it from history; exactly one line must print:
#   git log --format=%H --grep='update postgres 18.6-alpine -> 18.7-alpine on the two authentik helper CronJobs' origin/main
git revert --no-edit "$SHA"
git log -1 --format=%s           # PASS: Revert "chore(container): update postgres 18.6-alpine -> 18.7-alpine ..."
git show --stat HEAD             # PASS: exactly the two CronJob files
git push origin main
# If 4.6 already ran: confirm at the next sweep that the version check reports 18.6-alpine -> 18.7-alpine again for both CronJobs
# (a resolved row must not hide a rolled-back image); if it does not, record it with `policy-cli.py finding add`.

# clear any failed verification Job so kube_job_failed does not keep alerting on it
kubectl get jobs -n kube-system -o name | grep pg187-            # then: kubectl delete <each name printed> -n kube-system
```

Confirm the cluster is back (poll up to 5 min):

```bash
kubectl get cronjob authentik-channels-cleanup authentik-db-probe -n kube-system -o jsonpath='{.items[*].spec.jobTemplate.spec.template.spec.containers[0].image}' | tr ' ' '\n' | grep -c 'postgres:18.6-alpine@sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2'
# PASS: 2
```

Then prove the old image still works, because a rollback that is only a spec change is a shape check: wait for the next `:17` tick, or
repeat 4.2 and 4.3 with the old pin (expect imageID `d3e1620b...` or its amd64 child `63bdc97d...`). The old index digest was still
served by the registry on 2026-11-13 (pre-check 2.3 re-checks it), and the image is cached on the nodes that ran recent Jobs
(`imagePullPolicy: IfNotPresent`).

If the probe fails on BOTH images, the fault is not the image (database, secret, Pushgateway): stop rolling back and hand to the
operator with the Job log.

## 6. Interference notes

- **`postgres-digest-refresh-2026-11` (vetted, sun-attended:2026-12-20) edits the same two lines.** Its stage 1 runs
  `sed s/d3e1620b.../123b1799.../` over five files including both of these, commits them by path, and its close-out expects every
  `postgres:18.6-alpine` CronJob image to end in `123b1799...`. Once this plan has run, those two seds match nothing (silently) and that
  gate reads two CronJobs on `18.7-alpine` instead. Conversely, if the digest refresh runs first, this plan's first three premises fail
  and it must be refreshed (new `OLD` string). Whichever runs second needs an amendment; this plan is the one likely to run first.
  **Repo correction owed on that plan (not made here, this planner writes one file):** drop the two authentik CronJobs from its stage 1
  and close-out once this plan executes, and add `postgres-fleet-18.7-alpine` to its `conflicts_with` (reciprocity is not validated).
  Also observed 2026-11-13: the `18.6-alpine` tag now resolves to index `9ba53c7d...`, not the `123b1799...` that plan targets, so its
  own section 2 "tag rebuilt again: STOP" check will trip.
- **Sibling `postgres-fleet-18.7-bookworm` (authentik-pg, mealie-pg; draft, `autonomy_override: human-gated`, attended window).
  Declared in `depends_on`: bookworm runs FIRST.** Version compatibility does not force an order (an 18.7 client against an 18.6
  server and the reverse are both same-major), but the bookworm plan uses `authentik-db-probe` as one of its instruments (its section
  6.2), and changing the instrument's image before that measurement would make a failed probe ambiguous. The order used to live only
  in prose, which the scheduler does not read; a plan derived AUTO-NIGHT could otherwise have run on a nightly window before the attended
  bookworm window. It is enforced twice: `depends_on` (the scheduler skips this plan until bookworm is done) and the run-time premise
  pre-check 2.7 (fails while `authentik-pg` is still on 18.6, including after a bookworm rollback; deliberately not a premise, because `plan-premises.py` does not read `depends_on` and would fail the plan on every sweep until bookworm runs). The two plans **may share one
  window** (bookworm first, this plan after bookworm's 4.4 passed) and gain nothing from being merged. Run this plan's section 4 only
  while `authentik-pg` is Ready (premise `authentik-pg-ready`); if bookworm aborts and leaves it unhealthy, do not start this plan.
  Bookworm is not in `conflicts_with`: they are ordered, not mutually excluded.
- **Prometheus is the instrument.** Section 4.3 reads it, hence `kube-prometheus-stack-93.3.0` (PR #501, draft, exclusive) in
  `conflicts_with`; its exclusive flag already keeps it out of this plan's slot. The Pushgateway is a separate release; a same-night
  Pushgateway restart would also wipe the pushed group (it is in-memory) and fail 4.3 with `NO_SERIES`.
- **The manual probe run overwrites the Pushgateway group** `job=authentik-db-probe` with fresh values, exactly as the hourly run does.
  No alert input goes backwards.
- **Do not start section 4 on top of a scheduled tick** (pre-check 2.5). `concurrencyPolicy: Forbid` does not cover Jobs created by hand;
  two overlapping cleanup runs are harmless but make the log evidence ambiguous.
- **The other four `18.6-alpine` consumers in PR #504** (`superset-pg18`, `paperclip-postgresql`, `sweep-heartbeat`,
  `media-library-audit`) are outside this group and are not touched.
- **No Authentik pod restarts.** The Kustomization applies two CronJob specs; the HelmRelease, `authentik-pg` and the outposts are
  unchanged, so there is no login impact and nothing for the forward-auth path to notice.
- **Autonomy.** The declared facts derive AUTO-NIGHT (no capability change, git-revert, no reboot, no storage/flux/cni floor token).
  With `depends_on` it can only become eligible after the attended bookworm window has run. The planner's view is that the `*authentik*`
  hold does not by itself warrant `human-gated` here: no Authentik pod, chart or server image moves, the only database write is the
  same expired-row DELETE the CronJob already runs every 6h unattended, and the revert is complete. If the operator nonetheless means
  the glob as "attended for anything named authentik", add `autonomy_override: human-gated` at vetting; the alternative is narrowing
  the glob in `runbooks/auto-update-policy.yaml` (operator call, not this plan's).
