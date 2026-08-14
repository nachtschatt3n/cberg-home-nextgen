---
plan_id: media-episode-backfill
component: media-library
pr: null                              # content/metadata work, not a version bump
kind: data
current: "episode NFO 2.5% (20/807) · episode naming 87.7% (708/807) · 4 movies missing fanart"
target: "episode NFO >=80% (SOP floor) · naming >=99% · fanart gap closed"
update_type: n/a
risk: medium                          # file renames on a catastrophic-class CIFS share
est_duration_min: 120                 # across several sessions, one show per batch
needs_reboot: false
touches:
  namespaces: [media]
  resources:
    - "cifs-plex-media / cifs-jellyfin-media (READ-WRITE file operations)"
    - "library-tools sidecar.py (writes NFO/artwork)"
    - "Plex + Jellyfin libraries (rescan after each batch)"
  shared: [media]
depends_on: []
conflicts_with: []
status: draft
window: null                          # operator-paced; not a single-window job
auto_execute: false                   # NEVER unattended — see Interference
sops_refs:
  - docs/sops/media-library-standards.md
  - docs/sops/storage-safety.md
generated: "2026-08-15"
---

# Media: episode sidecar backfill + naming + the 4-item fanart cluster

## 1) Summary & why held

The 2026-08-14 audit — the first run that actually *measured* these — reports:

| Metric | Now | SOP floor |
|---|---|---|
| episode NFO coverage | **2.5%** (20/807) | ≥80% |
| episode naming | **87.7%** (708/807) | ≥99% |
| movies missing `fanart.jpg` | 4 | — |

**Concentrated, not scattered**, which is what makes it tractable: only 4 of 20
shows have any episode NFO at all (**16 shows have zero**), and all 99 naming
failures live in 4 shows.

**The 4-item fanart cluster is one root cause, proven not inferred:** the 4
folders missing `fanart.jpg` are *exactly* the 4 carrying an orphan `movie.nfo`,
and Jellyfin reports *exactly* 4/550 missing backdrops. `media-per-item-refresh`
has fired 4/4 repeatedly with no movement — a refresh cannot create a file that is
not on disk. One fix (write 4 `fanart.jpg`) clears three counters.

**Not included:** the "duplicate movies" backlog. It was re-adjudicated on
2026-08-14 — 16 of 18 TMDb-id collisions are a cohort of ~700 MB items with
*wrong TMDb uniqueids*, i.e. metadata mis-match, not disk duplication. That is
metadata repair with no deletion risk and belongs in its own pass. Only 2 groups
are genuine duplicate candidates and need `ffprobe` diffs before any go/no-go.

## 2) Pre-checks

```bash
# STORAGE SAFETY — read docs/sops/storage-safety.md first.
# cifs-plex-media and cifs-jellyfin-media are CATASTROPHIC class: a PVC delete
# wipes the entire share. This plan does file writes/renames ONLY.
# No PVC operations of any kind. Never `kubectl delete pvc` here.

# current numbers, from the CronJob (not by hand)
kubectl logs -n media job/$(kubectl get jobs -n media --sort-by=.metadata.creationTimestamp \
  -o name | grep media-library-audit | tail -1 | cut -d/ -f2) | grep '"section": "tv"'

# free space before writing hundreds of sidecars
kubectl exec -n media deploy/plex -- df -h /data/data | tail -1
```

## 3) Steps

Batch **one show per run**, operator go/no-go each time. Do not bulk-run.

1. **P1 — the 4 fanart files first.** Highest value per effort: clears
   `fanart_pct`, `movie_nfo_orphan` and the Jellyfin backdrop gap together. Write
   `fanart.jpg` from TMDb via `sidecar.py`; then delete the now-redundant orphan
   `movie.nfo`. Do **not** re-run `media-per-item-refresh` — proven ineffective.
2. **P2 — episode NFO backfill**, 16 shows / 787 episodes, one show per batch via
   `sidecar.py`. TV queries are hand-formatted per the TMDb ladder in the SOP
   (proper title, periods, umlauts) — a wrong series match writes 20+ wrong files.
3. **P3 — rename the 99 release-scene filenames** in 4 shows. Use the atomic
   multi-step rename from the SOP: media file → `.nfo` file → NFO XML fields →
   delete stale sidecars. Produce the rename table and have it approved BEFORE
   executing; a rename is the only step here that can lose a file.
4. Trigger a library rescan per batch (delegate to cluster-ops-agent) and confirm
   Plex/Jellyfin still match every item before the next batch.

## 4) Verification

```bash
# after each batch, re-run the audit and compare — do not trust the file writes
kubectl create job -n media audit-check-$(date +%s) --from=cronjob/media-library-audit
# expect episode_nfo_pct to climb monotonically; nothing else may regress
# (movies layout_pct, season_layout_pct, series_compliance_pct must stay put)

# Plex/Jellyfin still match everything (a bad rename shows up here, not on disk)
#   Plex: unmatched=0 in the fs-classifier output
#   Jellyfin: overview/primary stay 100%, backdrop 550/550 after P1
```

## 5) Rollback

- **P1/P2 are additive** — rollback is deleting the files that were added; the
  media files themselves are untouched.
- **P3 renames are the risky step.** Every rename is logged by the Job; roll back
  by replaying the log in reverse. Do one show, verify, and only then continue —
  the batch size IS the rollback boundary.
- Nothing here deletes media. If a step ever proposes deleting a media file, stop.

## 6) Interference notes

- `shared: [media]` — Plex, Jellyfin and Tube Archivist all read the same share.
  Rescans during a batch are expected; avoid running while someone is watching.
- **Never unattended.** `auto_execute: false` is load-bearing: this writes and
  renames files on a share whose PVC class wiped 4.7 TB once.
- Not a window job in the usual sense (`window: null`) — it is operator-paced
  across several sessions, one show at a time.
