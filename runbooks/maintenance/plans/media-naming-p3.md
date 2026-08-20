---
plan_id: media-naming-p3
component: media-library
pr: null
kind: data
current: "episode naming 49.9% (403/807) — 404 non-SOP filenames across 12 shows (was mis-reported as 87.7%/99 by a lax audit regex, corrected 2026-08-16)"
target: "episode naming >= 99% (SOP floor) — `Show Name - S01E01 - Episode Title.ext`"
update_type: n/a
risk: high                            # a rename is the only step in this family that can LOSE a file
est_duration_min: 240                 # was 60 (sized against the mis-reported 99). True surface is
                                      # 404 files / 12 shows → spans multiple weekend windows,
                                      # one show per batch. See §1.
needs_reboot: false
touches:
  namespaces: [media]
  resources:
    - "cifs-plex-media / cifs-jellyfin-media (file RENAMES — media files + their sidecars)"
    - "Plex + Jellyfin TV libraries (re-identification after each show)"
  shared: [media]
depends_on: [media-episode-backfill-bulk]
conflicts_with: []
status: draft
window: null                          # UNSCHEDULED 2026-08-16. Re-rated to 240m after the audit
                                      # regex was corrected (N-22): the real non-compliant surface is
                                      # 404 files across 12 shows, not 99 across 4 — the premise this
                                      # plan was sized against. 240m cannot fit any window (max 90m),
                                      # and it was silently sharing sat-early:2026-09-05 with
                                      # superset-pg-decommission (270m of 90m) — invisible until the
                                      # reconciler's 14-day horizon blind spot was fixed the same day.
                                      #
                                      # SPLIT before rescheduling, one-show-per-batch like the other
                                      # oversized plans. Each batch is independently verifiable
                                      # (series_compliance stays measurable) and revertible. Do NOT
                                      # co-schedule with superset-pg-decommission (that slot is the
                                      # soak-gated 09-05 window; leave it to the DB work).
                                      # (7 windows/week, was 4). Deliberate soaks are
                                      # preserved, not compressed — see the windows YAML.
auto_execute: false                   # NEVER unattended — operator-approved rename table required
sops_refs:
  - docs/sops/media-library-standards.md
  - docs/sops/storage-safety.md
generated: "2026-08-15"
---

# Media stage 4/4 — rename the 404 non-SOP episode filenames (attended)

## 0) Independently re-verified 2026-08-20 — and the surface is softer than 404 suggests

The 49.9% figure was confirmed by a read-only scan of the actual filenames,
run outside the audit so a second bad regex could not agree with the first.
It reproduces the audit exactly, and the *reason* it differs from the old
87.7% is now pinned down:

| reading | compliant | pct |
|---|---|---|
| any prefix before ` - SxxEyy - ` | 616 | 76.3% |
| prefix **equals the show folder** (the SOP rule) | **403** | **49.9%** |

So the audit is right and the old 87.7% was the lax-regex artifact.

**CORRECTION 2026-08-20 (second pass).** A first reading of this called the
213 "a mechanical prefix substitution, do them first". **That was wrong and
generating the rename table is what caught it.** The table came out proposing
to rewrite correctly-named files to match malformed folders — it would have
damaged 213 good filenames. Do not restore that framing.

The 404 splits into two unrelated problems:

- **213 files across just 2 shows are FOLDER-side.** The filenames are already
  correct; the *folder* disagrees with them. One folder is concatenated without
  periods or spaces while its 43 files carry the properly punctuated title; the
  other folder drops a separator its 170 files include. The remedy is
  **2 folder renames and zero file renames**, which is a completely different
  risk profile from 213 file operations. Caveat: renaming a show folder changes
  the library path, so Plex/Jellyfin re-match the series — check watch state and
  artwork after, and do it as its own step.
- **191 files across 12 shows are genuine file-naming faults** — 99 carry an
  `SxxEyy` but no ` - ` separators, 92 deviate otherwise. **This, not 404, is
  the real file-rename surface**, and the 240-minute estimate should be re-sized
  against it.

**One show cannot be fixed by renaming alone.** It holds 52 files numbered
continuously `S01E01..S01E52`, while TMDb lists 26 episodes in season 1 —
verified by forcing the series id from its own `tvshow.nfo`. Episodes 27-52
therefore match nothing and received no sidecar in the NFO backfill. They
need a season split (`S02Exx`) before either naming or NFO coverage can
reach them; a prefix-only rename will not help.


## 1) Summary & why held

Final stage. 404 of 807 episodes do not match the SOP form
`Show Name - S01E01 - Episode Title.ext`; `episode_naming_pct` is **49.9%**
against a ≥99% floor.

**Scope correction (2026-08-16, sweep N-22):** this stage was originally sized
against "99 filenames in 4 shows / 87.7%". That figure came from a lax audit
regex (` - SxxEyy\b`, case-insensitive, no prefix/title constraint) that measured
a *weaker* rule than the SOP mandates and under-counted the surface ~4x. The audit
now measures the real SOP rule — case-sensitive `SxxExx` token, filename prefix
equal to the show folder name, and a non-empty episode title — so the true surface
is **404 files across 12 shows** (10 of which are fully non-compliant; the largest
single show holds 173). Nothing on disk changed; only the measurement was corrected.

**This is materially bigger than the family assumed and no longer fits one window.**
At one-show-per-batch with per-show go/no-go it spans **multiple weekend windows**.
`est_duration_min` was raised 60 → 240 to reflect that; the maintenance-window
agent will split it across windows rather than force it into one.

**This is the only stage in the family that can lose data.** Every other stage writes
additive sidecars whose rollback is "delete what was added". A rename mutates the file
that *is* the media. It therefore runs last, attended, in a weekend window, with an
operator-approved rename table produced **before** anything moves.

**It runs after the NFO backfill, not before, and the ordering is load-bearing.** After
`media-episode-backfill-bulk` each episode has a `.nfo` whose basename must match the
media file. A rename that moves `X.mkv` without also moving `X.nfo` silently orphans
the sidecar and drops `episode_nfo_pct` right back down. The SOP's multi-step rename
exists for exactly this:

1. media file → 2. the matching `.nfo` → 3. the NFO's XML fields → 4. delete stale sidecars.

**Why the rename table is the real deliverable.** The dangerous failure is not a
crashed job; it is a rename that collides (two source files mapping to one target) or
that mis-parses an episode number and swaps two episodes. Both are invisible in the
counters afterwards — `episode_naming_pct` goes up either way.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) STORAGE SAFETY — docs/sops/storage-safety.md first. cifs-plex-media /
#    cifs-jellyfin-media are CATASTROPHIC class. This stage RENAMES files in place.
#    No PVC operation of any kind. Never `kubectl delete pvc` in this window.
#    Renames must be move-only (the organize.py invariant): never copy-then-delete.

# b) baseline + confirm stage 3 held
mise exec -- kubectl create job -n media audit-pre-$(date +%s) --from=cronjob/media-library-audit
mise exec -- kubectl logs -n media job/audit-pre-<id> | grep -E '"section": "(tv|movies)"'
# record: episode_naming_pct (49.9 pre-stage, corrected metric), episode_nfo_pct (>=80 after stage 3),
# season_layout_pct 100.0, series_compliance_pct 100.0.

# c) THE deliverable — produce the rename table and have it APPROVED before any move.
#    For each of the 12 affected shows, list: current filename -> proposed filename, plus the
#    matching .nfo and -thumb.jpg. Keep it OUTSIDE the repo (public repo: no titles).
#    Validate the table mechanically before showing it to the operator:
#      * every target matches the SOP regex `<Show> - S\d\dE\d\d( - .+)?\.(mkv|mp4|avi|m4v)`
#      * TARGETS ARE UNIQUE — a collision would overwrite a real episode
#      * no target already exists on disk
#      * every source has exactly one target and vice versa (a bijection)
#      * season/episode numbers are taken from the EXISTING SxxEyy in the source name
#        where present; where absent, the operator confirms the mapping by hand
#      * umlauts stay as `ä/ö/ü` — the SOP forbids transliteration and CIFS handles UTF-8

# d) free space + servers healthy + nobody watching
mise exec -- kubectl exec -n media deploy/plex -- df -h /data/data | tail -1
mise exec -- kubectl get pods -n media | grep -E 'plex|jellyfin'
mise exec -- kubectl logs -n media deploy/plex --since=30m | grep -i 'playing' | tail -5 || echo "no active playback"
```

## 3) Steps

Operator go/no-go **per show**, against the approved table. One show per batch.

1. **Marker**:
   ```bash
   runbooks/update-marker.sh add media-library media 2 "episode filename normalisation — 12 shows, approved rename table"
   ```
2. **Dry-run the rename job for one show** and diff its output against the approved
   table — the job must propose exactly the approved moves, no more:
   ```bash
   mise exec -- kubectl create job -n media rename-dry-$(date +%s) --from=cronjob/media-organize
   #   scoped to SHOW_PATH=<show>, dry-run mode
   mise exec -- kubectl logs -n media job/rename-dry-<id> | tee /tmp/rename-proposed.txt
   diff /tmp/rename-approved-<show>.txt /tmp/rename-proposed.txt    # must be empty
   ```
3. **Execute for that show**, following the SOP's 4-step order (media file → `.nfo` →
   NFO XML fields → stale sidecars). Every rename must be logged by the Job — the log is
   the rollback script.
4. **Immediately verify that show** before starting the next: episode count on disk
   unchanged, no orphaned `.nfo`, Plex/Jellyfin still match every episode (§4).
5. **Rescan** after each show and confirm the server re-identified the renamed files
   rather than creating duplicates:
   ```bash
   mise exec -- kubectl create job -n media rescan-$(date +%s) --from=cronjob/media-rescan
   ```
6. **Stop at the window boundary.** A show is atomic; stopping between shows leaves a
   consistent library. Do not start a show with less than 15 minutes left — a rename
   rollback is slower than a rename.
7. Clear the marker: `runbooks/update-marker.sh clear media-library`.

## 4) Verification

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) FIRST: nothing was lost. Episode COUNT is the primary safety metric here —
#    a collision silently reduces it.
mise exec -- kubectl create job -n media audit-post-$(date +%s) --from=cronjob/media-library-audit
mise exec -- kubectl logs -n media job/audit-post-<id> | grep '"section": "tv"'
```

| metric | expected |
|---|---|
| `episodes_total` | **exactly 807** (or the current baseline) — any drop means a rename collided |
| `episode_naming_pct` | up toward ≥ 99.0 for the shows processed |
| `episode_nfo_pct` | **unchanged** — if it fell, `.nfo` files were orphaned by their media file |
| `season_layout_pct` | still 100.0 |
| `series_compliance_pct` | still 100.0 |
| movies metrics | untouched |

```bash
# b) THE load-bearing check — the servers re-identified the files rather than
#    creating duplicate or unmatched items
mise exec -- kubectl create job -n media coverage-$(date +%s) --from=cronjob/media-metadata-coverage
mise exec -- kubectl logs -n media job/coverage-<id> | tail -30
#   Plex: unmatched=0 in all 3 sections — a bad rename shows up HERE, not on disk
#   Jellyfin: overview 100%, primary 100%, backdrop still 546/550
mise exec -- kubectl create job -n media fsclass-$(date +%s) --from=cronjob/media-plex-fs-classifier
mise exec -- kubectl logs -n media job/fsclass-<id> | tail -30
#   no new skip_dir_leftover / duplicate buckets

# c) per show, by hand: open the renamed show in Jellyfin and confirm episode ORDER and
#    titles are right. An off-by-one that swapped two episodes leaves every counter
#    perfect and the library wrong — this check is the only thing that catches it.

# d) no orphaned sidecars
#    For each renamed show, confirm every .nfo has a media file with the same basename
#    (the audit's episode_nfo_pct covers this in aggregate; spot-check one season).
```

Success = episode count unchanged, `episode_naming_pct` ≥ 99 for the processed shows,
`episode_nfo_pct` and `series_compliance_pct` unchanged, Plex `unmatched=0`, no new
fs-classifier findings, and hand-verified episode order.

## 5) Rollback

**Replay the rename log in reverse, per show.** Every rename is logged by the Job; the
log is the rollback script, which is why one show per batch is a hard rule.

```bash
# 1. Take the rename log for the affected show (the Job's output).
mise exec -- kubectl logs -n media job/rename-<show>-<id> > /tmp/rename-executed.txt
# 2. Invert it: target -> source, in REVERSE order, so any intermediate name is free
#    when it is needed again.
# 3. Execute via an ephemeral Job mounting the same PVC (move-only; never copy-delete).
# 4. Do the same for the .nfo and -thumb.jpg moves, and restore the NFO XML fields
#    (<title>/<season>/<episode>) that step 3 of the SOP rename rewrote.
#
# NEVER delete the PVC. cifs-plex-media is catastrophic class (docs/sops/storage-safety.md).
```

Then prove the library is back:

```bash
mise exec -- kubectl create job -n media audit-rb-$(date +%s) --from=cronjob/media-library-audit
mise exec -- kubectl logs -n media job/audit-rb-<id> | grep '"section": "tv"'
# episodes_total unchanged, episode_naming_pct back to the pre-show value,
# episode_nfo_pct unchanged, series_compliance_pct 100.0
mise exec -- kubectl create job -n media rescan-rb-$(date +%s) --from=cronjob/media-rescan
mise exec -- kubectl create job -n media coverage-rb-$(date +%s) --from=cronjob/media-metadata-coverage
# Plex unmatched=0
```

**If a file cannot be found after a rename, do not improvise a delete.** The move-only
invariant means it still exists somewhere — search both the show folder and the section
root for the basename (`docs/sops/media-library-standards.md`, "Diagnose Example 1").
Nothing in this plan deletes a media file; if any step proposes it, stop.

## 6) Interference notes

- **Out of order:** running this before `media-episode-backfill-bulk` is not merely
  premature — it changes the work. Rename first and the later NFO backfill writes
  sidecars for the new names (fine); backfill first and rename second means each rename
  must carry its `.nfo` along (the SOP's 4-step order). This plan is written for the
  second case. If the backfill has **not** run, the rename table must be rebuilt without
  the `.nfo` steps, and this plan re-verified — do not execute it as written.
- **`shared: [media]`** — Plex, Jellyfin and Tube Archivist read the same share. Renames
  cause re-identification; expect items to briefly disappear from the UI during a scan.
  Do not co-schedule any other `media` plan and do not run while anyone is watching.
- **Never unattended.** `auto_execute: false` is load-bearing twice over: an approved
  rename table is required *and* per-show go/no-go is required.
- **Public repo:** the rename table, the show names and the episode titles must never be
  committed, pasted into a commit message, or written into a runbook artefact. Keep the
  table outside the repo; report counts only.
- **The window's slack is the rollback budget.** 60 min of work in a 90 min window is
  deliberate: replaying a rename log in reverse takes longer than the original rename.
  If a show fails verification, spend the remaining time rolling that show back rather
  than starting the next one.
- After this stage the whole `media-episode-backfill` family is complete: episode NFO
  ≥80%, naming ≥99%, and the movie fanart gap closed as WONTFIX (4 items with no
  upstream backdrop; `fanart_pct` 99.2 against a ≥90 floor).
