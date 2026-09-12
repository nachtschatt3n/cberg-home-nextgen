---
plan_id: grafana-duplicate-provisioning-row
component: grafana
pr: null
kind: config
current: "two dashboard_provisioning rows point at the SAME file .../sidecar/default/prometheus.json
  (row 1836 -> dashboard 201, row 1864 -> dashboard 204). The provisioner resolves the file to
  dashboard 201, writes the file's uid 9fa0d141, and collides with dashboard 204 which already
  holds that uid -- every 30s, forever."
target: "one file maps to one dashboard: only row 1864 -> 204 remains, the sidecar writes 204
  successfully, and prometheus.json can receive upstream updates again"
update_type: state-repair
risk: low
est_duration_min: 25
needs_reboot: false
supersedes: grafana-orphan-dashboard-uid
touches:
  namespaces: [monitoring]
  resources:
    - deployment/grafana
    - pvc/grafana-config          # sqlite lives here
  shared: []
depends_on: []
conflicts_with: []
capability_change: false
backup_gate: "(a) ConfigMap monitoring/kube-prometheus-stack-prometheus key prometheus.json must
  exist and carry uid 9fa0d141-d019-4ad7-8bc5-42196ee308bd -- it IS the restore path for the
  dashboard content; absent or empty means STOP. (b) a copy of grafana.db taken OFF the
  grafana-config PVC, proven with `pragma integrity_check` = ok AND proven QUERYABLE (row counts
  read back), not merely openable. Both must pass before any write."
rollback_class: backup-restore    # the change is a DELETE of one row; there is no commit to
                                  # revert. See section 6 -- the re-INSERT is a one-liner and the
                                  # exact row contents are recorded there, so the practical
                                  # rollback is cheap.
status: draft                     # REWRITTEN 2026-09-12 from grafana-orphan-dashboard-uid, which
                                  # was BLOCKED on a false premise and, critically, named the
                                  # WRONG row. See section 5.
window: null
sops_refs:
  - docs/sops/grafana-image-changes.md
  - docs/sops/monitoring.md
premises:
  - id: error-still-occurring
    why: >-
      If the collision has stopped on its own (an upstream re-provision, a
      restart that reconciled it), there is nothing to repair and this plan
      must not write to the database.
    run: kubectl logs -n monitoring deploy/grafana -c grafana --since=5m | grep -c "same uid already exists"
    expect_matches: "^[1-9][0-9]*$"
  - id: configmap-still-ships-the-colliding-uid
    why: >-
      The whole mechanism depends on the provisioned file carrying uid
      9fa0d141. If upstream changed the uid again, a FOURTH dashboard has
      probably been created and the row mapping must be re-measured before
      touching anything.
    run: kubectl get cm kube-prometheus-stack-prometheus -n monitoring -o jsonpath='{.data.prometheus\.json}' | grep -c '9fa0d141-d019-4ad7-8bc5-42196ee308bd'
    expect_matches: "^[1-9][0-9]*$"
  - id: kube-prometheus-stack-chart-unchanged
    why: >-
      kube-prometheus-stack OWNS prometheus.json (grafana's own chart does
      not ship it). A chart move may change the dashboard's content or its
      uid, which invalidates the row analysis in section 2.
    run: kubectl get helmrelease kube-prometheus-stack -n monitoring -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "90.0.0"
  - id: grafana-helmrelease-ready
    why: "Do not perform state repair on an already-failing release."
    run: kubectl get helmrelease grafana -n monitoring -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: grafana-image-unchanged
    why: >-
      Measurements in section 2 were taken against 13.2.1. A different Grafana
      binary may provision differently; re-measure rather than assume.
    run: kubectl get deploy grafana -n monitoring -o jsonpath='{range .spec.template.spec.containers[?(@.name=="grafana")]}{.image}{end}'
    expect_exact: "docker.io/grafana/grafana:13.2.1-distroless"
generated: "2026-09-12"
---

# Grafana: one file, two provisioning rows

## 0. Decision memo — answering "why delete? we still have Prometheus"

**The recommended fix deletes NO dashboard.** All three "Prometheus / Overview"
dashboards stay exactly where they are. What gets removed is a single stale
internal pointer row that maps a file to the wrong dashboard.

That reframing matters, because the previous plan really did propose the wrong
thing — and it named the wrong record while doing it.

## 1. What the three dashboards actually ARE (measured, not inferred from titles)

Extracted all three from an integrity-checked copy of `grafana.db` and compared
their JSON with uid/version/id normalised out:

```
normalised content hash          bytes
148        a9b120e20163976e083d   11059
201        a9b120e20163976e083d   11059   <- IDENTICAL to 148
204        9fe4506a16d9b7ca6f8a   11062
ConfigMap  9fe4506a16d9b7ca6f8a   11062   <- IDENTICAL to 204
```

- **148 and 201 are byte-identical to each other.**
- **204 is byte-identical to the ConfigMap the sidecar ships today.**
- All four carry the **same 15 panels** with the same titles.

The only difference between the two generations is upstream churn:
`pluginVersion: v11.4.0` -> `v13.0.0` on eleven panels, and one panel's
`unit: ms` -> `unit: short`. Those are chart-shipped changes, not human edits.

**No dashboard here contains unique hand-made work.** Confirmed independently:
every row in `dashboard_version` for all three has `created_by = -1`
(system/provisioning). **No human has ever saved any of them.** So "duplicate"
is the right word, and nothing of the operator's is at stake.

### Is any of them in use?

Checked every reference Grafana records:

| Signal | Result |
|---|---|
| Starred | none (the DB holds exactly 1 star, on an unrelated dashboard) |
| Playlists | zero playlists exist at all |
| Alert rules referencing the uids | 0 for all three |
| Library-panel connections | 0 |
| Annotations attached | 0 |
| Home-dashboard pinning (`preferences`) | table is empty |

Nothing points at any of the three. Grafana's OSS build does not retain
per-dashboard view counts, so "has a human opened it" is not answerable from
the database — stated as a limit rather than guessed at. What IS certain is
that **204 is the one the sidecar maintains and the one matching current
upstream content**, so it is the one a user should be looking at.

### Provisioned vs user-created

| id | uid | provisioning row | status | reproducible from ConfigMap? |
|---|---|---|---|---|
| 148 | `05081011-…` | **none** | effectively user-created (orphaned in Jan) | no — but it is a byte-identical copy of an older 201 |
| 201 | `a3b1fd60-…` | 1836 (stale, Jan) | provisioned | no — its uid is not in any ConfigMap |
| 204 | `9fa0d141-…` | 1864 (current) | provisioned | **yes — this is the one the sidecar regenerates** |

Only **204** would be recreated if it vanished. 148 and 201 would not — but
their content is identical to an older generation of 204, so nothing unique
would be lost either.

## 2. Root cause: how three arrived

`dashboard_provisioning` rows in insert order show the pattern clearly. Every
sidecar dashboard has exactly ONE row, and ~50 of them share the timestamp
`2026-07-17 01:24:44` — a mass re-provision (the power-outage restart).

```
1836  ->  dashboard 201   updated 2026-01-23 15:09:58   prometheus.json   <- STALE
1864  ->  dashboard 204   updated 2026-07-17 01:24:44   prometheus.json   <- current
```

Row 1864 carries the same timestamp as all its healthy siblings. Row 1836 was
left at January and never re-provisioned.

The sequence:

1. **2026-01-23 ~15:08-15:10** — initial provisioning. Dashboard 148 is created,
   then 201 one second later; 148 loses its provisioning row to 201.
2. **2026-02-07 21:02** — a chart upgrade re-provisions dashboards (neighbouring
   row 1830 shares that timestamp). Upstream had **changed prometheus.json's
   uid** to `9fa0d141`, so the sidecar created a **new** dashboard (204) rather
   than updating 201 — Grafana keys provisioned dashboards by uid.
3. **2026-07-17 01:24** — mass re-provision after the power outage. Row 1864 is
   refreshed; row 1836 is not.

**The defect is that the upstream chart changed the dashboard's UID, and the
provisioning row for the previous uid was never cleaned up.** Grafana has no
self-heal path for two rows on one file: neither row is an orphan (both point at
existing dashboards and an existing file), so nothing garbage-collects them.

### Is it systemic?

No — and this is reassuring. Across 67 provisioning rows and 81 dashboards:

- exactly **one** `external_id` has duplicate rows (`prometheus.json`)
- **zero** provisioning rows point at a non-existent dashboard
- exactly **one** title+folder duplicate (`Prometheus / Overview`)

This is a single historical accident, not a pattern.

### Does the queued Grafana chart bump re-trigger it?

**No.** `prometheus.json` is shipped by **kube-prometheus-stack**, not by the
grafana chart — verified from the ConfigMap label set. The queued
`grafana-chart-13.2.3` bump carries appVersion 13.2.1 unchanged and ships no
dashboard JSON, so it neither causes nor fixes this.

**The one to watch is `kube-prometheus-stack 90.0.0 -> 90.1.1`, currently in the
HELD lane.** If that bump changes prometheus.json's uid again, a FOURTH
dashboard appears. And while the collision persists, **204 cannot receive
updated content at all** — which is the real cost of doing nothing (section 3).

## 3. Options, non-destructive first

**Option A — do nothing.**
Cost today is genuinely zero functionally: 204 already matches the ConfigMap
byte-for-byte, so the write the sidecar keeps failing is a **no-op it is failing
to perform**. The dashboard renders correctly. The price is ~2,880 log lines/day
poisoning the error stream, plus three identical entries in dashboard search.
**But it is not purely cosmetic:** because the write never succeeds, dashboard
204 is **frozen** — the next time upstream changes prometheus.json (e.g. the
held kube-prometheus-stack bump), the update will silently not apply and the
dashboard will quietly drift out of date with no new signal. That is a latent
update-blocker, and it is the honest argument against "just leave it".
*Legitimate choice if the operator prefers zero writes — but it should be made
knowing the dashboard is frozen, not believing it is harmless noise.*

**Option B — move 148/201 into a folder.**
**Does not work.** The error is a **uid** collision, and Grafana enforces uid
uniqueness per organisation, independent of folder. Moving folders changes
nothing about which dashboard holds `9fa0d141`. Rejected on mechanism, not taste.

**Option C — change the uid of 148/201 so they stop colliding.**
**Does not work either.** The collision is not caused by 201's *current* uid; it
is caused by the provisioner *writing the file's* uid (`9fa0d141`) onto
dashboard 201, where it meets 204. Re-uid-ing 201 leaves the same write hitting
the same wall. The only way to stop the collision by uid-editing would be to
change **204's** uid — which would deliberately desynchronise it from the file
it is supposed to mirror. Rejected.

**Option D — re-point row 1836 at dashboard 204 (an UPDATE, not a DELETE).**
Tempting, and genuinely non-destructive in spirit. But it leaves **two rows both
mapping the same file to the same dashboard**, which is a state Grafana does not
produce on its own and whose behaviour is unvalidated — it may well keep
erroring. It trades a known-bad state for an untested one, at the same write
cost as the correct fix. Not recommended, but it is the best fallback if the
operator wants the row preserved rather than removed.

**Option E — delete the ConfigMap so Grafana's own cleanup reconciles.**
Grafana deletes provisioned dashboards when their file disappears, so a
remove-then-restore cycle would clear both rows and rebuild cleanly. But this
deletes **dashboards** (via Grafana's own logic) rather than a pointer, is a much
bigger hammer, and means editing a ConfigMap owned by the kube-prometheus-stack
chart. Strictly worse than Option G on every axis.

**Option F — change the sidecar provider config (`allowUiUpdates`,
`disableDeletion`, distinct folder).**
Addresses none of it. These control *future* provisioning behaviour; they do not
reconcile the two rows that already exist. It is worth noting the previous plan
already established that `disableDeletion: false` does not help. Rejected.

**Option G — delete the stale provisioning row 1836. RECOMMENDED.**
One row. **No dashboard is deleted.** 148, 201 and 204 all remain untouched in
the database. Afterwards `prometheus.json` maps to exactly one dashboard (204,
via row 1864), the sidecar's write succeeds against content it already matches,
the errors stop, and future upstream updates land again. Dashboard 201 simply
becomes an ordinary DB dashboard — exactly what 148 already is today.

**Why 1836 and not 1864 — and why the previous plan was wrong.**
Row 1864 is the healthy, current record: it points at the dashboard whose
content matches the ConfigMap, and it carries the same re-provision timestamp as
every one of its ~50 healthy siblings. Row 1836 is the January leftover that the
July re-provision did not touch. **The superseded plan proposed deleting 1864 —
the correct row — which would have destroyed the good mapping and left the
broken one in place.** That is the strongest reason this plan exists.

## 4. Recommendation

**Option G**, or **Option A** if the operator would rather accept a frozen
dashboard than any write. Both are defensible; G is a single-row change with a
recorded re-INSERT, A is free but leaves prometheus.json permanently unable to
update.

Do **not** take B, C, E or F — B and C do not work, E and F are strictly worse.

## 5. Pre-checks

```bash
# MECHANICAL — run the checker; exit 1 = do not execute
python3 runbooks/plan-premises.py grafana-duplicate-provisioning-row

# MANUAL DB GATE — NOT mechanisable. plan-premises.py's allowlist is
# cluster/git-local (kubectl/flux/talosctl/helm/git + text filters); it cannot
# query sqlite. So the row-level facts below must be re-measured BY HAND from a
# read-only copy before any write. Do not let a green premise run stand in for
# this -- that substitution is exactly what let the superseded plan reach an
# approved GO on a false premise.
#
#   REQUIRE, on a fresh copy of grafana.db:
#     select id, dashboard_id from dashboard_provisioning
#      where external_id like '%sidecar/default/prometheus.json';
#   EXPECT EXACTLY TWO ROWS: 1836 -> 201 and 1864 -> 204.
#   If the ids or mappings differ, STOP and re-derive section 2.
```

**Reading the DB read-only, without restarting Grafana.** The image is
`-distroless` (no shell) and has no `sqlite3`, and an ephemeral container
inherits uid 472 so `apk add` fails. Read the file through the target's
filesystem and analyse it **off-cluster**:

```bash
kubectl debug -n monitoring <grafana-pod> --image=alpine:3 --target=grafana \
  -c dbread -- sh -c 'sleep 300'
kubectl exec -n monitoring <grafana-pod> -c dbread -- \
  sh -c 'cd /proc/1/root/var/lib/grafana && tar cf - grafana.db' > /tmp/gdb.tar
```

**NEVER run `kill 1` inside that ephemeral container.** `--target` shares the
PID namespace, so PID 1 is *Grafana's* process — doing so restarted Grafana on
2026-09-12. Let the `sleep` expire, or exit the shell.

## 6. Steps, and the rollback held ready

Record the exact row contents **before** removing anything — this IS the
rollback:

```
id=1836  dashboard_id=201  name='sidecarProvider'
external_id='/var/lib/grafana/dashboards/sidecar/default/prometheus.json'
updated=1769180998  (2026-01-23T15:09:58Z)
check_sum: capture with `select check_sum from dashboard_provisioning where id=1836;`
```

Then delete that one row by **id** (never by `external_id`, which would match
both):

```sql
DELETE FROM dashboard_provisioning WHERE id = 1836;
```

**Rollback** (no pod restart needed either way; the provisioner re-reads every 30s):

```sql
INSERT INTO dashboard_provisioning
  (id, dashboard_id, name, external_id, updated, check_sum)
VALUES (1836, 201, 'sidecarProvider',
        '/var/lib/grafana/dashboards/sidecar/default/prometheus.json',
        1769180998, '<recorded check_sum>');
```

Full fallback: restore `grafana.db` from the backup-gate copy.

## 7. Verification

```bash
# 1. the errors must STOP -- measure over a real interval, not one line
kubectl logs -n monitoring deploy/grafana -c grafana --since=10m | grep -c "same uid already exists"
# EXPECT: 0  (baseline before the change is ~20 per 10 min)

# 2. exactly ONE provisioning row for the file now
#    EXPECT: 1864 -> 204 only

# 3. NOTHING was lost -- all three dashboards still present
#    EXPECT: ids 148, 201, 204 all still in `dashboard`; total dashboards still 81

# 4. the dashboard still renders and is the CURRENT content
#    EXPECT: uid 9fa0d141... resolves, 15 panels, pluginVersion v13.0.0

# 5. grafana healthy
kubectl get pod -n monitoring -l app.kubernetes.io/name=grafana
# EXPECT: 3/3 Running, no new restarts
```

A zero in check 1 with a dashboard missing in check 3 is a FAILURE, not a pass —
check them together.

**Proof the fix actually unblocks updates** (the point of doing it at all):
after the change, the provisioner's next write to 204 should succeed. Confirm
`dashboard.version` for id 204 increments, or that the log shows no further
failures across a full 10-minute interval.

## 8. Interference

Shares namespace `monitoring` with `edot-collector-0.160.0` and the
kube-prometheus-stack chart. Serialise — do not run concurrently with either.
Must NOT be co-scheduled with a kube-prometheus-stack bump, which is the one
change that can alter the dashboard this plan is reasoning about.
