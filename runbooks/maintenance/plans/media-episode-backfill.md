---
plan_id: media-episode-backfill
component: media-library
pr: null                              # content/metadata work, not a version bump
kind: data
current: "episode NFO 2.5% (20/807) · episode naming 87.7% (708/807) · 4 movies missing fanart"
target: "episode NFO >=80% (SOP floor) · naming >=99% · fanart gap CLOSED AS WONTFIX (see §1a)"
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
status: blocked                       # P1 wontfix · P2 blocked on missing tool · P3 deferred
window: null                          # CANNOT BE SCHEDULED AS WRITTEN (found 2026-08-15).
                                      # est_duration_min is 120m but the LONGEST window in
                                      # runbooks/maintenance-windows.yaml is 90m (sat/sun;
                                      # tue/thu are 60m). This plan does not fit any slot, so
                                      # leaving it window:null is not an oversight — it must be
                                      # SPLIT into stages that each fit inside a window with
                                      # rollback slack, or run as an attended out-of-window
                                      # operation with explicit operator go/no-go.
auto_execute: false                   # NEVER unattended — see Interference
sops_refs:
  - docs/sops/media-library-standards.md
  - docs/sops/storage-safety.md
generated: "2026-08-15"
revised: "2026-08-15"                 # revised after execution attempt — see §1a
---

# Media: episode sidecar backfill + naming + the 4-item fanart cluster

> **REVISION 2026-08-15 — READ §1a BEFORE EXECUTING ANYTHING.**
> An execution attempt on 2026-08-15 found that **P1 and P2 as originally
> written are both non-executable**, and that two of the originally specified
> steps would have caused *regressions*. The original §3 steps are retained
> below only as struck-through history. §1a is now the authoritative status.

## 1) Summary & why held

The 2026-08-14 audit — the first run that actually *measured* these — reports:

| Metric | Now | SOP floor | Verdict |
|---|---|---|---|
| episode NFO coverage | **2.5%** (20/807) | ≥80% | real gap, blocked on missing tool |
| episode naming | **87.7%** (708/807) | ≥99% | real gap, deferred (P3) |
| movies missing `fanart.jpg` | 4 | — (`fanart_pct` floor is ≥90%) | **not a failure — 99.2% passes** |

**Concentrated, not scattered**, which is what makes it tractable: only 4 of 20
shows have any episode NFO at all (**16 shows have zero**), and all 99 naming
failures live in 4 shows.

**Not included:** the "duplicate movies" backlog. It was re-adjudicated on
2026-08-14 — 16 of 18 TMDb-id collisions are a cohort of ~700 MB items with
*wrong TMDb uniqueids*, i.e. metadata mis-match, not disk duplication. That is
metadata repair with no deletion risk and belongs in its own pass. Only 2 groups
are genuine duplicate candidates and need `ffprobe` diffs before any go/no-go.

## 1a) REVISION — findings from the 2026-08-15 execution attempt

### P1 — WONTFIX. The fanart cannot be written; the upstream has no image.

The original root-cause claim was **correct**: the 4 folders missing
`fanart.jpg` are exactly the 4 carrying an orphan `movie.nfo`, and Jellyfin
reports exactly `with_backdrop_image: 546/550`. One cluster, three counters.

But the prescribed *fix* is impossible. All 4 folders already carry a TMDb id in
their `<folder>.nfo`, so there is **no matching risk** — the ids were queried
directly against the TMDb `/movie/{id}/images` and `/movie/{id}` endpoints:

| Item | `backdrop_path` | backdrops (all langs, incl. `null`/`xx`) | posters |
|---|---|---|---|
| movie #1 | `None` | 0 | 1 |
| movie #2 | `None` | 0 | 1 |
| movie #3 | `None` | 0 | 1 |
| movie #4 | `None` | 0 | 1 |

`sidecar.py` guards the fanart write with `if item.get("backdrop_path"):`
(`kubernetes/apps/media/library-tools/app/scripts-configmap.yaml:811`). With
`backdrop_path` null it writes **nothing**. Running it would not have produced a
single file. All 4 are obscure documentaries/shorts (TMDb popularity 0.86–1.70)
— the long-tail remainder, which is *why* they are the ones left over.

The plan's reasoning ("a refresh cannot create a file that is not on disk") was
right about why `media-per-item-refresh` loops uselessly, but the replacement
fails one level deeper: there is nothing upstream to fetch.

**`fanart_pct` is 99.2% against a ≥90% SOP floor — this was never a compliance
failure.** Per the SOP repair-pass rule ("skip if even the upstream is too low —
escalate as *best available*"), these 4 are now recorded as **best available**.
Synthesizing artwork (e.g. an ffmpeg frame-grab) to move a counter that already
passes its floor was considered and **declined** by the operator 2026-08-15.

### P1's `movie.nfo` deletion — SUPERSEDED. Do not do it.

The original step 1 ended "then delete the now-redundant orphan `movie.nfo`".
That is harmful as written, for three independent reasons:

1. **The "orphan" is the *richer* file.** `movie.nfo` carries director, rating,
   runtime, genre, country, studio, IMDb id and stream details. The canonical
   `<folder>.nfo` is the minimal 5-field form — and for at least one of the 4 it
   is *worse* than minimal (a drifted `<title>` with a trailing digit and an
   empty `<plot>`). Deleting the orphan is a net metadata **downgrade** here.
2. **It self-reverts within hours.** All 4 `movie.nfo` files were regenerated by
   the servers at 2026-08-14 20:00. A Jellyfin FullRefresh rewrites them.
3. **It is already automated.** The weekly `media-cleanup-nfos` CronJob
   (Sun 04:30) performs exactly this deletion.

The orphan cluster was instead removed **at its source** — see §1c.

### P2 — BLOCKED ON A MISSING TOOL, not on effort.

`episode_nfo_pct` counts a `.nfo` beside **each episode file** (`audit.py`:
`ep.with_suffix(".nfo").exists()`). But **no per-episode NFO writer exists
anywhere in `library-tools`**:

- `sidecar.py` writes exactly **one file per invocation** — `<folder>.nfo` for
  `ITEM_KIND=movie`, or `tvshow.nfo` for `ITEM_KIND=show`. It has no episode path.
- `common.py`'s TMDb helpers have no `/tv/{id}/season/{n}` endpoint.
- Nothing in the ConfigMap emits an `<episodedetails>` document.
- `per_item_refresh.py` only calls server-side refresh APIs; it writes no files.

**P2 therefore requires `episode_sidecar.py` to be written and code-reviewed
FIRST, in an attended session.** Scope for that tool: TMDb season/episode
endpoints, `<episodedetails>` schema per the SOP, per-season fetch, `--dry-run`,
and a per-show batch boundary. Only then can the 787-episode backfill run — one
show at a time, starting with a canary (see the trap below).

### P2's specified method would have caused a REGRESSION — the `.nfo` unlink trap

**This is the dangerous part of the original plan and the reason to read this
section before retrying.** `sidecar.py` **unlinks every `.nfo` in the target
folder before writing** (`scripts-configmap.yaml:805`):

```python
for f in item_path.iterdir():
    if f.is_file() and f.suffix.lower() == '.nfo':
        try: f.unlink()
```

Run per-show with `ITEM_KIND=show` — exactly as originally specified — it would
have **deleted each show's existing `tvshow.nfo`** and rewritten it from a fresh
TMDb match. `series_compliance_pct` is currently **100.0%** across all 20 shows.
A single bad series match would have driven a currently-perfect metric down,
while still writing **zero** episode NFOs (the actual objective). The tool named
in the plan put the very metric the plan's own verification gate requires to
hold directly at risk.

### P2 canary selection — two shows hit documented TMDb ladder traps

Two of the 16 shows are the exact traps called out in the SOP's TMDb query
ladder and will return **nothing** if queried as their folder name:

- one show's folder name is a **de-umlauted German title** — needs the proper
  umlaut form;
- one show's folder name is **concatenated without periods or spaces** — needs
  the properly punctuated title.

Both require a hand-formatted `TMDB_QUERY`. **Start the canary on a clean,
unambiguous show instead**, and hold these two until the tool is proven.

### P3 — unchanged, still deferred

Explicitly excluded from the 2026-08-15 run. A rename is the only step here that
can lose a file; it stays attended.

## 1c) DONE 2026-08-15 — the one change that was executed

The only actionable defect was the **futile refresh loop**, and it was fixed at
the source rather than by deleting files that come straight back.

`media-per-item-refresh` re-detected the 4 items as "missing backdrop" every 6h
and fired a Jellyfin `FullRefresh` at each one, forever. That loop was not
harmless: each FullRefresh **rewrites `movie.nfo`** on the share, continuously
regenerating the redundant sidecars that `media-cleanup-nfos` then deletes
weekly — the two CronJobs were fighting each other indefinitely.

**Change:** `REFRESH_SKIP_ART_ONLY=1` (new, default on) in
`per_item_refresh.py` + `per-item-refresh-cronjob.yaml`. Items whose *only*
missing field is the backdrop/art image are skipped, on both the Plex (`art`)
and Jellyfin (`backdrop`) paths. Items missing `overview`/`summary` or the
primary/thumb poster still refresh normally — those are genuinely fixable; the
art-only case is the one retrying can never fix.

The gap stays **visible**: `media-metadata-coverage` still measures and reports
`backdrop_pct`. This suppresses pointless write traffic, not the metric. Both
Jobs now log a `skipped_art_only` count. Set the env to `"0"` to restore the
previous behaviour.

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

1. ~~**P1 — the 4 fanart files first.** Write `fanart.jpg` from TMDb via
   `sidecar.py`; then delete the now-redundant orphan `movie.nfo`.~~
   **SUPERSEDED 2026-08-15 — see §1a.** TMDb has no backdrop for any of the 4;
   `sidecar.py` writes nothing. Recorded as *best available*. The orphan
   `movie.nfo` deletion is harmful and already covered by `media-cleanup-nfos`.
   The refresh loop was fixed instead (§1c). **Nothing left to do for P1.**
2. ~~**P2 — episode NFO backfill**, 16 shows / 787 episodes, one show per batch
   via `sidecar.py`.~~ **BLOCKED 2026-08-15 — `sidecar.py` cannot write episode
   NFOs and would delete each `tvshow.nfo` (§1a).** Prerequisite: author and
   review `episode_sidecar.py` in an **attended** session, then backfill one
   show per batch starting with a clean canary.
3. **P3 — rename the 99 release-scene filenames** in 4 shows. Use the atomic
   multi-step rename from the SOP: media file → `.nfo` file → NFO XML fields →
   delete stale sidecars. Produce the rename table and have it approved BEFORE
   executing; a rename is the only step here that can lose a file. **Still
   deferred — attended only.**
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
#   Jellyfin: overview/primary stay 100%; backdrop stays 546/550 (4 = upstream
#             gap, WONTFIX per §1a — do NOT treat 550/550 as the target)
```

Baseline recorded 2026-08-15 (unchanged by the §1c fix, which writes no files):

- movies: 508 items · `layout_pct` 99.6 · `nfo_pct` 100.0 · `poster_pct` 99.0 ·
  `fanart_pct` 99.2 · `movie_nfo_orphan` 4
- tv: 20 shows · 807 episodes · `episode_nfo_pct` 2.5 ·
  `season_layout_pct` 100.0 · `series_compliance_pct` 100.0
- Plex: `unmatched=0` in all 3 sections, summary/thumb/art 100%
- Jellyfin: 550 items · overview 100% · primary 100% · backdrop 546/550 (99.3%)
- share: 25 T free of 33 T (26% used)

## 5) Rollback

- **§1c (executed)** — revert the introducing commit, or set
  `REFRESH_SKIP_ART_ONLY=0` in `per-item-refresh-cronjob.yaml`. No file writes,
  so there is nothing on the share to undo.
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
- **Lesson from 2026-08-15:** this plan named a tool (`sidecar.py`) that could
  not perform the task and whose actual behaviour (unlink-all-nfo) would have
  regressed a passing metric. Verify the tool can do the thing *and* check what
  else it touches, before scheduling the batch — not during it.
