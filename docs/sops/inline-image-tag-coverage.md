# SOP: Inline CronJob/Job Image Tag Coverage

> Description: Closes the gap where container image tags written directly
> (inline) into `kind: CronJob`/`kind: Job` pod templates are invisible to
> `runbooks/check-all-versions.py` and, by extension, `runbooks/coverage.py` —
> so they are never version-checked and `CRACK 0` does not mean "none
> uncovered", it means "not looked at".
> Version: `2026.09.05`
> Last Updated: `2026-09-05`
> Owner: `platform-sre`

---

## 1) Description

`runbooks/check-all-versions.py` builds its universe of "things to
version-check" from two sources only:

1. `find_helmreleases()` — every `*helmrelease.yaml` / `*helm-release.yaml`
   file (picks up chart version + any `image:` overrides in `values:`).
2. `find_raw_manifest_workloads()` — raw-manifest files (no HelmRelease)
   whose top-level `kind` is `Deployment`, `StatefulSet`, or `DaemonSet`
   (`_RAW_WORKLOAD_KINDS`, `runbooks/check-all-versions.py:541`).

A raw manifest with `kind: CronJob` or `kind: Job` matches **neither**
source: it isn't a HelmRelease, and `_RAW_WORKLOAD_KINDS` does not include
`CronJob`/`Job`. Its inline `image:` therefore never enters
`version-check-current.md`, never enters `coverage.py`'s universe (which is
built entirely by parsing that file — see `coverage.py`'s own header), and
never gets a stale-version finding no matter how far behind it drifts.

This is the **same class of bug**, fixed once already for
Deployment/StatefulSet/DaemonSet on 2026-08-24 (see the docstring on
`find_raw_manifest_workloads()`), recurring for CronJob/Job. That fix's
lesson applies verbatim: an honest "0 uncovered" requires a complete
denominator; a silent gap in the denominator is not a clean result, it is an
unmeasured one.

- Scope: every `kind: CronJob` / `kind: Job` manifest under
  `kubernetes/apps/**` whose pod template sets `image:` directly (i.e. NOT
  rendered from a HelmRelease chart's `values:`).
- Prerequisites: `kubectl` access to the cluster (for the live-vs-repo
  cross-check in §6), read access to this repo.
- Out of scope: CronJobs/Jobs that a Helm chart renders from HelmRelease
  `values:` (e.g. `pallet-price-monitor`, `descheduler`, the Longhorn
  recurring-job CronJobs, `nextcloud-cron`) — those are already inside
  `find_helmreleases()`'s reach, or share the separately-documented
  "HelmRelease never overrides `values.image`" sibling gap noted in
  `find_raw_manifest_workloads()`'s docstring. Also out of scope: image bump
  *mechanics* for immutable Jobs — that's
  [`docs/sops/immutable-job-image-bumps.md`](immutable-job-image-bumps.md).

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Namespace | all (`kubernetes/apps/**`, cluster-wide) |
| Source of truth | `runbooks/check-all-versions.py` (`_RAW_WORKLOAD_KINDS`, line 541) |
| Downstream consumer | `runbooks/coverage.py` (reads `version-check-current.md`, does not touch the cluster or repo itself) |
| Verified surface (2026-09-05) | 22 raw-manifest files (20 CronJob + 2 Job), 8 unique images, 3 digest-pinned / 5 floating-tag |
| Related finding | F-e432896d (this SOP), F-9188fdb8 (why the first close-by-absence didn't count) |

---

## 3) Blueprints

N/A as a deployable blueprint — this SOP documents an **audit gap**, not a
component with its own manifest. The relevant "blueprint" is the code
location that needs to change:

```python
# runbooks/check-all-versions.py:541
_RAW_WORKLOAD_KINDS = ("Deployment", "StatefulSet", "DaemonSet")
```

---

## 4) Operational Instructions

### 4.1 How to enumerate the inline-tag surface today (manual, until the code changes)

Two independent enumerations should agree — cluster-live and repo-static.
Disagreement means either an object was deployed out-of-band (no manifest)
or a manifest exists but was never applied; both are worth chasing.

**A. Cluster-live** (every CronJob's actual running image):

```bash
kubectl get cronjob -A -o json | python3 -c "
import json, sys
d = json.load(sys.stdin)
for item in d['items']:
    ns, name = item['metadata']['namespace'], item['metadata']['name']
    spec = item['spec']['jobTemplate']['spec']['template']['spec']
    for c in spec.get('containers', []) + spec.get('initContainers', []):
        print(f'{ns}/{name}\t{c[\"name\"]}\t{c[\"image\"]}')
"
```

**B. Repo-static** (raw-manifest files, excludes HelmRelease-rendered
CronJobs/Jobs):

```bash
grep -rlE '^kind: (CronJob|Job)$' kubernetes/apps/ | while read -r f; do
  # HelmRelease-rendered CronJobs live INSIDE a HelmRelease values: block,
  # never as a literal top-level `kind: CronJob` doc — this pattern already
  # excludes them.
  grep -H 'image:' "$f" | sed "s|^|$f: |"
done
```

### 4.2 What would need to change in code to close the gap

This has NOT been implemented — the finding is closed by *documenting the
gap and the fix path precisely*, per the finding's own action text ("nothing
documents that..."). If/when implemented:

1. **`Job` can be added to `_RAW_WORKLOAD_KINDS` directly.** A `Job`'s pod
   spec lives at `spec.template.spec` — structurally identical to
   Deployment/StatefulSet/DaemonSet. The existing extraction code in
   `find_raw_manifest_workloads()`:
   ```python
   pod_spec = (((doc.get('spec') or {}).get('template') or {}).get('spec') or {})
   ```
   already handles it correctly with zero changes beyond the tuple.

2. **`CronJob` needs a new extraction branch**, because its pod spec is one
   level deeper:
   ```python
   pod_spec = ((((doc.get('spec') or {}).get('jobTemplate') or {})
                .get('spec') or {}).get('template') or {}).get('spec') or {}
   ```
   Cleanest approach: keep `_RAW_WORKLOAD_KINDS` as the "flat" set (add
   `Job`), and add a second constant/branch for `CronJob` that uses the
   `jobTemplate`-aware extraction, feeding into the same
   HelmRelease-shaped-dict output so the rest of `check_all()`'s per-image
   loop needs zero duplication (this mirrors exactly how
   `find_raw_manifest_workloads()` was designed to slot into the existing
   loop — see its docstring).

3. **`coverage.py` needs no direct change.** It builds its universe entirely
   by parsing `version-check-current.md` (Quick Overview Table + per-app
   detail sections). Once step 1–2 land, CronJob/Job entries flow into that
   file the same way raw Deployment/StatefulSet/DaemonSet entries already
   do, and `coverage.py` picks them up for free — this is the same
   cascade that happened automatically on 2026-08-24.

4. **Do not silently absorb HelmRelease-rendered CronJobs into this fix.**
   `pallet-price-monitor`, `descheduler`, the Longhorn recurring-job
   CronJobs, and `nextcloud-cron` are chart-rendered; their coverage status
   (full, partial-via-chart-default, or the "never overrides values.image"
   sibling gap) is orthogonal to this SOP and must not be conflated with it
   in a future fix's commit message or tests.

---

## 5) Examples

### Example A: confirm a specific CronJob is currently invisible

```bash
grep -c "authentik-channels-cleanup\b.*postgres" runbooks/version-check-current.md
# Expect: 0 (the image never appears in the audit's own output)
```

### Example B: the lockstep trap — a client tag that must track a server tag

`kubernetes/apps/kube-system/authentik/app/cronjob-channels-cleanup.yaml`
pins `postgres:18.6-alpine@sha256:...` as a `psql` **client** used to purge
expired Django Channels messages from authentik's database. The database
itself is `kubernetes/apps/kube-system/authentik/app/pg-deployment.yaml`,
pinned to `postgres:18.6-bookworm` — the current source of truth for
authentik's Postgres version (superseding the bundled 17.11 StatefulSet in
`helmrelease.yaml`, see the comment there).

These two tags are **not independently upgradable**: bump the server's major
version without bumping the CronJob's `psql` major version (or vice versa)
and you risk protocol/feature mismatches on every 6-hourly run. Because
neither image is in the audit denominator today, an ordinary version-check
pass would never flag this pair as "these two must move together" — a
human (or a future `coverage.py` lane) has to know to check both files
whenever either changes.

```bash
# Verify the pair is still in lockstep before touching either file
grep -H 'image: postgres' \
  kubernetes/apps/kube-system/authentik/app/pg-deployment.yaml \
  kubernetes/apps/kube-system/authentik/app/cronjob-channels-cleanup.yaml
# Expect: both lines show the same MAJOR.MINOR (18.6)
```

### Example C: digest-pinned vs floating-tag inline images (verified 2026-09-05)

```
digest-pinned (3 images, 4 files):
  postgres:18.6-alpine@sha256:...           sweep-heartbeat, authentik-channels-cleanup
  busybox:stable@sha256:...                 paperclip-backup-cleanup
  pgvector/pgvector:0.8.6-pg16@sha256:...   sweep-history-init-v6 (Job)

floating-tag (5 images, 18 files):
  docker.io/rancher/kubectl:v1.36.2         frigate-restart
  python:3.14.7-slim                        11 files (mealie-shopping-sync, openclaw-probe,
                                             9x media/library-tools CronJobs)
  python:3.11-slim                          tube-archivist image-sync + metadata-sync
  docker.io/library/python:3.12-alpine      crash-ghost-reaper, elasticsearch-obs-recovery
  curlimages/curl:8.22.0                    elasticsearch-otel-ilm-bootstrap (Job)
```

---

## 6) Verification Tests

### Test 1: cluster-live count matches repo-static count (denominator completeness)

```bash
LIVE=$(kubectl get cronjob -A --no-headers | wc -l)
# Subtract the known HelmRelease-rendered CronJobs (not in scope for this SOP):
# pallet-price-monitor, descheduler, nextcloud-cron, + N Longhorn recurring-job CronJobs
HELM_RENDERED=$(kubectl get cronjob -n storage --no-headers | wc -l)  # Longhorn recurring jobs
HELM_RENDERED=$((HELM_RENDERED + 3))  # pallet-price-monitor, descheduler, nextcloud-cron
REPO_RAW=$(grep -rlE '^kind: CronJob$' kubernetes/apps/ | wc -l)
echo "live=$LIVE  helm-rendered=$HELM_RENDERED  repo-raw-cronjob=$REPO_RAW"
```

Expected:
- `live - helm_rendered == repo_raw_cronjob` (every raw-manifest CronJob in
  git has exactly one live counterpart, and vice versa — no orphans in
  either direction).

If failed:
- `live > expected`: something was `kubectl apply`'d outside GitOps —
  investigate before trusting any audit output for that namespace.
- `repo_raw > live`: a manifest was added/renamed but Flux hasn't
  reconciled it (or the Kustomization is failing) — check
  `flux get kustomizations -A`.

### Test 2: the denominator claim is falsifiable, not assumed

```bash
# Pick any raw-manifest image from §4.1B and confirm it is ABSENT from the
# audit's own output — this is the test that proves the gap exists, not
# just that it's plausible.
python3 runbooks/check-all-versions.py --help >/dev/null  # sanity: script runs
grep -q "docker.io/rancher/kubectl:v1.36.2" runbooks/version-check-current.md \
  && echo "UNEXPECTED: now covered — re-verify this SOP's scope" \
  || echo "CONFIRMED: still outside the denominator"
```

Expected:
- `CONFIRMED` today. If this ever prints `UNEXPECTED`, the code fix in §4.2
  landed — update this SOP's §2 "Verified surface" and §4.2 status instead
  of leaving it describing a gap that no longer exists.

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| `coverage.py` reports `CRACK 0` but a CronJob image is known-stale | Denominator incomplete (this SOP's gap) — `CRACK 0` means "not looked at", not "clean" | Run §4.1's manual enumeration; don't trust `CRACK 0` alone for CronJob/Job coverage until §4.2 lands |
| New CronJob added to the repo, never shows up anywhere in version tracking | `_RAW_WORKLOAD_KINDS` still excludes `CronJob`/`Job` | Add it to §6 Test 1's tracking manually; flag for the code fix in §4.2 |
| A HelmRelease-rendered CronJob (e.g. Longhorn recurring job) looks "covered" but its image tag never updates | Sibling gap: HelmRelease exists but never overrides `values.image`, so the chart's own default is invisible too — different bug, same *family*, see `find_raw_manifest_workloads()` docstring | Out of scope for this SOP; needs a chart-values resolver (noted as future work in the code) |
| Authentik channels-cleanup CronJob fails after a Postgres bump | Lockstep break (§5 Example B) — server and client tag diverged | Check both `pg-deployment.yaml` and `cronjob-channels-cleanup.yaml` MAJOR.MINOR match; re-pin the digest deliberately, per the `security_ref: F-31aadd6f` comment in the CronJob file |

```bash
# Quick debugging: is a given image string anywhere in the audit output?
grep -F "<image:tag>" runbooks/version-check-current.md || echo "NOT in denominator"
```

---

## 8) Diagnose Examples

### Diagnose Example 1: "is this specific CronJob's image tracked at all?"

```bash
IMG="python:3.14.7-slim"
grep -F "$IMG" runbooks/version-check-current.md
```

Expected:
- No output (as of 2026-09-05) confirms the file is in this SOP's gap.

If unclear:
- Cross-check the file is a **raw** `kind: CronJob` manifest (not
  HelmRelease-rendered) via `grep -B5 'image: '"'"'$IMG'"'"'' <file>` and
  confirm no `kind: HelmRelease` appears above it in the same file.

### Diagnose Example 2: "did the code fix in §4.2 actually land?"

```bash
grep -n "CronJob\|_RAW_WORKLOAD_KINDS" runbooks/check-all-versions.py
```

Expected:
- `_RAW_WORKLOAD_KINDS` includes `"Job"`, and a separate `CronJob`-aware
  extraction branch exists (the `jobTemplate.spec.template.spec` path).

If unclear:
- Run Test 2 (§6) — if it now prints `UNEXPECTED: now covered`, the fix
  landed even if the code search above was inconclusive (e.g. renamed
  function).

---

## 9) Health Check

```bash
# Re-run the live-vs-repo count check periodically (e.g. each sweep) to
# catch NEW CronJobs/Jobs added to the gap before they drift silently.
LIVE=$(kubectl get cronjob -A --no-headers | wc -l)
REPO_RAW=$(grep -rlE '^kind: CronJob$' kubernetes/apps/ | wc -l)
echo "live cronjobs: $LIVE   repo raw-manifest cronjobs: $REPO_RAW"
```

Expected:
- Counts stay proportionally consistent with §6 Test 1's baseline
  (22 raw-manifest files as of 2026-09-05). A jump in `REPO_RAW` without a
  corresponding update to this SOP's §2/§5 counts means new surface has
  entered the gap unnoticed.

---

## 10) Security Check

```bash
# Floating-tag inline images are lower-assurance than digest-pinned ones —
# a `docker pull` on next scheduler run can silently change what runs.
grep -rE '^kind: (CronJob|Job)$' -A0 -l kubernetes/apps/ | while read -r f; do
  grep -H 'image:' "$f"
done | grep -v '@sha256:'
```

Expected:
- Matches only the floating-tag set documented in §5 Example C (5 images,
  18 files) — no *new* floating-tag inline image without a deliberate
  reason.
- No CVE IDs, per-image vulnerability counts, or unfixed-vulnerability
  detail added to this file or any commit touching it — reference
  `security_ref: F-xxxxxxxx` instead (see
  `docs/sops/vulnerability-disclosure.md`).

---

## 11) Rollback Plan

This SOP is documentation-only; there is no live change to roll back. If a
future commit implements §4.2's code change and it misbehaves (e.g. floods
`version-check-current.md` with noise, or double-counts a HelmRelease-
rendered CronJob):

```bash
git log --oneline -- runbooks/check-all-versions.py | head -5
git revert <commit-that-added-CronJob/Job-support>
```

---

## 12) References

- `runbooks/check-all-versions.py` — `_RAW_WORKLOAD_KINDS` (line 541),
  `find_raw_manifest_workloads()` (the 2026-08-24 precedent fix for
  Deployment/StatefulSet/DaemonSet)
- `runbooks/coverage.py` — universe-building header comment (own warning
  about denominator completeness)
- `runbooks/doc-check.py` — `find_repo_subworkloads()`, the same
  denominator-class bug applied to documentation coverage instead of
  version coverage
- `docs/sops/immutable-job-image-bumps.md` — how to actually bump an
  inline Job/CronJob image once it's known to be stale
- `docs/sops/vulnerability-disclosure.md` — disclosure boundary for any
  vulnerability detail touching these images
- Findings: F-e432896d (this SOP), F-9188fdb8 (why an earlier close-by-
  absence of this same gap didn't count), F-31aadd6f (authentik
  channels-cleanup digest-pin rationale), F-62007db7 (self-built-image
  lane matching precedent referenced in `coverage.py`)

---

## Version History

- `2026.09.05`: Initial version. Closes F-e432896d. Verified live surface:
  36 CronJobs total (20 raw-manifest `kind: CronJob` files + 16
  HelmRelease-rendered: 13 Longhorn recurring jobs + pallet-price-monitor
  + descheduler + nextcloud-cron), plus 2 raw `kind: Job` files (22
  raw-manifest files total). 8 unique images across the raw-manifest set
  (3 digest-pinned, 5 floating). Documented the authentik
  channels-cleanup/pg-deployment lockstep trap and the exact code path to
  close the gap in `check-all-versions.py`.
