#!/usr/bin/env python3
"""Regression test for the media-library audit CronJob's Music section
(kubernetes/apps/media/library-tools/app/scripts-configmap.yaml, audit.py,
2026-08-24).

Two bugs, found together because the second was hiding behind the first:

  1. `common.SECTIONS` has defined `"music"` since the file was written, and
     `docs/sops/media-library-standards.md` has a Music row in its
     audit-thresholds table (Layout >=95%, NFO >=80%, folder.jpg >=80%) --
     but `main()` only ever called `(audit_movies, audit_tv)`. No
     `audit_music()` existed. A threshold that is never measured is not a
     passing threshold; it's an absent one, and absence had been silently
     read as "nothing to report" for as long as the section existed.

  2. `main()`'s "Worst compliance metric" reduced over EVERY key ending in
     `_pct` across every section's result dict, including ones the SOP
     threshold table never defines a row for: `episode_thumb_pct`
     (thumbnails are a required sidecar per the Naming rules section, but
     never got a numeric threshold), `episode_naming_pct`, and `nested_pct`
     (structural stats, not compliance targets). A low, untracked metric
     could make the headline read as a near-total library failure while
     every SOP-defined threshold was passing -- exactly what happened with
     episode_thumb_pct, reproduced below.

Run: python3 runbooks/tests/test-media-audit-music-section.py
"""
import pathlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CM = (REPO_ROOT / "kubernetes/apps/media/library-tools/app/scripts-configmap.yaml")
PASS = FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        print(f"  PASS  {name}")
        PASS += 1
    else:
        print(f"  FAIL  {name}\n        got {got!r}\n        want {want!r}")
        FAIL += 1


if not shutil.which("kubectl") and not CM.exists():
    print("  SKIP  scripts-configmap.yaml not found")
    sys.exit(0)

try:
    import yaml
except ImportError:
    print("  SKIP  PyYAML not installed")
    sys.exit(0)

doc = yaml.safe_load(CM.read_text())
audit_src = doc["data"]["audit.py"]
common_src = doc["data"]["common.py"]

import ast
check("audit.py parses as valid Python", (lambda: (ast.parse(audit_src), True)[1])(), True)

check("audit_music() is defined", "def audit_music()" in audit_src, True)
check("check_album() is defined", "def check_album(" in audit_src, True)
check("main() calls audit_music alongside audit_movies/audit_tv",
      bool(re.search(r"for fn in \(audit_movies,\s*audit_tv,\s*audit_music\)", audit_src)),
      True)

# --- the worst-metric allowlist -------------------------------------------
m = re.search(r"TRACKED_PCT_KEYS = \{(.*?)\}", audit_src, re.S)
check("TRACKED_PCT_KEYS allowlist exists", m is not None, True)
tracked_body = m.group(1) if m else ""
for must_have in ("layout_pct", "nfo_pct", "poster_pct", "fanart_pct",
                  "season_layout_pct", "episode_nfo_pct", "series_compliance_pct"):
    check(f"TRACKED_PCT_KEYS includes {must_have!r}", must_have in tracked_body, True)
for must_not_have in ("episode_thumb_pct", "episode_naming_pct", "nested_pct"):
    check(f"TRACKED_PCT_KEYS EXCLUDES {must_not_have!r} (no SOP threshold row)",
          f'"{must_not_have}"' in tracked_body, False)
check("the worst-metric loop is now gated on the allowlist, not a bare "
      "'.endswith(\"_pct\")'",
      'if k in TRACKED_PCT_KEYS and isinstance(v, (int, float))' in audit_src, True)

# --- end-to-end: run the REAL extracted audit.py against a synthetic tree -
def make_png(path, width, height):
    sig = b"\x89PNG\r\n\x1a\n"
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"\x00" + b"\xff\x00\x00" * width
    idat = zlib.compress(raw * max(height, 1))
    path.write_bytes(sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b""))


with tempfile.TemporaryDirectory() as td:
    td = pathlib.Path(td)
    app_dir = td / "app"
    app_dir.mkdir()
    (app_dir / "common.py").write_text(common_src)
    (app_dir / "audit.py").write_text(
        audit_src.replace('sys.path.insert(0, "/app")', f'sys.path.insert(0, {str(app_dir)!r})')
    )

    media = td / "media"
    (media / "Movies").mkdir(parents=True)
    (media / "TV Shows").mkdir(parents=True)
    (media / "Music").mkdir(parents=True)

    # a fully-compliant album
    a1 = media / "Music" / "Artist A" / "Album One (2021)"
    a1.mkdir(parents=True)
    (a1 / "01 - Track.flac").touch()
    (a1 / "album.nfo").write_text("<album><title>Album One</title></album>")
    make_png(a1 / "folder.jpg", 700, 700)

    # an album missing NFO and folder.jpg -- non-compliant, but still nested
    a2 = media / "Music" / "Artist B" / "Album Two (2019)"
    a2.mkdir(parents=True)
    (a2 / "01 - Track.flac").touch()

    # a flat artist -- loose tracks, no album layer at all (layout violation)
    a3 = media / "Music" / "Artist C"
    a3.mkdir(parents=True)
    (a3 / "loose-track.mp3").touch()

    proc = subprocess.run(
        [sys.executable, str(app_dir / "audit.py")],
        env={"MEDIA_ROOT": str(media), "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True, timeout=30,
    )
    out = proc.stdout
    check("audit.py runs end-to-end without crashing", proc.returncode, 0)
    check("the music section appears in the summary", "- music:" in out, True)

    m2 = re.search(r"- music: items=(\d+), nested=(\d+), flat=(\d+), compliant=(\d+), "
                   r"layout_pct=([\d.]+), nested_pct=([\d.]+), nfo_pct=([\d.]+), "
                   r"poster_pct=([\d.]+)", out)
    check("the music summary line has the expected shape", m2 is not None, True)
    if m2:
        items, nested, flat, compliant, layout_pct, nested_pct, nfo_pct, poster_pct = m2.groups()
        check("music: 3 total items (2 albums + 1 flat artist)", items, "3")
        check("music: 2 nested (album-layer) items", nested, "2")
        check("music: 1 flat (loose-track) artist", flat, "1")
        check("music: exactly 1 fully-compliant album (Album One)", compliant, "1")
        check("music: layout_pct is 2/3 (66.7) -- the flat artist fails layout",
              layout_pct, "66.7")
        check("music: nfo_pct is 1/2 nested (50.0) -- only Album One has album.nfo",
              nfo_pct, "50.0")
        check("music: poster_pct is 1/2 nested (50.0) -- only Album One has folder.jpg",
              poster_pct, "50.0")

    # --- reproduce the exact reported symptom: episode_thumb_pct=0 must not
    # sink the headline when every SOP-tracked metric is otherwise fine -----
    show = media / "TV Shows" / "Test Show" / "Season 01"
    show.mkdir(parents=True)
    (media / "TV Shows" / "Test Show" / "tvshow.nfo").write_text(
        "<tvshow><title>Test Show</title><year>2020</year></tvshow>")
    make_png(media / "TV Shows" / "Test Show" / "poster.jpg", 700, 1000)
    make_png(media / "TV Shows" / "Test Show" / "fanart.jpg", 1400, 800)
    (show / "Test Show - S01E01 - Pilot.mkv").touch()
    (show / "Test Show - S01E01 - Pilot.nfo").write_text(
        "<episodedetails><season>1</season><episode>1</episode>"
        "<title>Pilot</title><aired>2020-01-01</aired></episodedetails>")
    # deliberately NO -thumb.jpg -- episode_thumb_pct will be exactly 0%

    mov = media / "Movies" / "Test Movie (2020)"
    mov.mkdir(parents=True)
    (mov / "Test Movie (2020).mkv").touch()
    (mov / "Test Movie (2020).nfo").write_text(
        "<movie><title>Test Movie</title><year>2020</year></movie>")
    make_png(mov / "poster.jpg", 700, 1000)
    make_png(mov / "fanart.jpg", 1400, 800)

    (a2 / "album.nfo").write_text("<album><title>Album Two</title></album>")
    make_png(a2 / "folder.jpg", 700, 700)

    proc2 = subprocess.run(
        [sys.executable, str(app_dir / "audit.py")],
        env={"MEDIA_ROOT": str(media), "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True, timeout=30,
    )
    out2 = proc2.stdout
    thumb_m = re.search(r"episode_thumb_pct=([\d.]+)", out2)
    check("episode_thumb_pct is genuinely 0.0 in this fixture (the reported symptom)",
          thumb_m.group(1) if thumb_m else None, "0.0")
    worst_m = re.search(r"Worst compliance metric \(SOP-tracked thresholds only\): ([\d.]+)%", out2)
    check("the worst-metric line uses the new SOP-tracked label", worst_m is not None, True)
    if worst_m:
        worst = float(worst_m.group(1))
        # Every SOP-tracked metric here is 100 except music's layout/nfo/poster
        # (66.7 from the deliberate flat artist) -- so the true worst is 66.7,
        # not the untracked episode_thumb_pct's 0.0.
        check("the headline is NOT dragged to 0% by the untracked "
              "episode_thumb_pct -- this is the fix",
              worst > 0, True)
        check("the headline reflects a genuine SOP-tracked shortfall (66.7, "
              "music layout/nfo/poster from the flat artist), not a false 100",
              worst, 66.7)

print(f"\n  {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
