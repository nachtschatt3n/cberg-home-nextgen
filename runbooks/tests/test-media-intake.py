#!/usr/bin/env python3
"""Regression tests for the automatic JDownloader intake (2026-09-28).

Covers kubernetes/apps/media/library-tools/app/scripts-configmap.yaml
(intake.py, organize.py, cleanup.py, rescan.py, common.py) and the
media-intake-watcher CronJob wiring. Tmpdir fixtures only, no real media:
a fixture "video" is a small file whose CONTENT is the JSON the fake ffprobe
returns, so size and probe values are both under the test's control.

  1. classification (tv / movie / music / youtube / ambiguous)
  2. the four quality outcomes incl. the fps rule (identical, better, worse,
     undecidable) — both decide() and end-to-end through run()
  3. two-step replace ORDER (library copy -> _duplicates first) and a
     mid-failure rollback
  4. EXDEV refusal (atomic_mv and the run preflight)
  5. .rar / recent-mtime skip
  6. `?` in titles
  7. dry-run immutability (INTAKE_APPLY=0 changes nothing on disk)
  8. cleanup refusing when a destination is missing / media is left
  9. the >50-items safety stop
 10. rescan is folder-scoped only (no full-library calls)
 11. manifests: single share-root mount, TTLs, alert rule labels + absent()

Run: python3 runbooks/tests/test-media-intake.py
"""
import importlib
import json
import os
import pathlib
import shutil
import sys
import tempfile
import time

REPO = pathlib.Path(__file__).resolve().parents[2]
APPDIR = REPO / "kubernetes/apps/media/library-tools/app"
CM = APPDIR / "scripts-configmap.yaml"
PASS = FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        print(f"  PASS  {name}")
        PASS += 1
    else:
        print(f"  FAIL  {name}\n        got  {got!r}\n        want {want!r}")
        FAIL += 1


try:
    import yaml
except ImportError:
    print("  SKIP  PyYAML not installed")
    sys.exit(0)

TMP = pathlib.Path(tempfile.mkdtemp(prefix="intake-test-"))
SCRIPTS = TMP / "app"
SCRIPTS.mkdir()
for k, v in yaml.safe_load(CM.read_text())["data"].items():
    (SCRIPTS / k).write_text(v)

SHARE = TMP / "share"
MEDIA = SHARE / "data"
INTAKE = SHARE / "downloads" / "jdownloader"
os.environ.update({
    "MEDIA_ROOT": str(MEDIA), "JDOWNLOADER_ROOT": str(INTAKE), "APP_DIR": str(SCRIPTS),
    "INTAKE_APPLY": "1", "INTAKE_RESCAN": "0", "INTAKE_SIDECARS": "0",
    "TMDB_API_KEY": "", "PUSHGATEWAY_URL": "",
    "INTAKE_METRICS_FILE": str(TMP / "metrics.prom"),
})
os.environ.pop("GIT_INDEX_FILE", None)
sys.path.insert(0, str(SCRIPTS))
import common as C  # noqa: E402
import organize  # noqa: E402
import cleanup as CL  # noqa: E402
import rescan as R  # noqa: E402
import intake as I  # noqa: E402

OLD = time.time() - 3 * 3600


def reset():
    if SHARE.exists():
        shutil.rmtree(SHARE)
    for s in ("Movies", "TV Shows", "Music"):
        (MEDIA / s).mkdir(parents=True)
    INTAKE.mkdir(parents=True)
    I.APPLY = True
    I.MAX_ITEMS = 50
    I.TMDB_KEY = ""
    I.tmdb_movie = lambda t, y: None
    I.tmdb_show = lambda n: None


def vid(path, w=1920, h=1080, fps=23.976, dur=6000.0, br=8_000_000, pad=0, age=OLD):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"width": w, "height": h, "fps": fps, "duration": dur, "bit_rate": br})
    path.write_text(body + " " * pad)
    os.utime(path, (age, age))
    return path


def aud(path, album, artist, title, track, disc=None, year="2001", br=320_000, age=OLD):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tags = {"album": album, "album_artist": artist, "artist": artist, "title": title,
            "track": str(track), "date": year}
    if disc:
        tags["disc"] = str(disc)
    path.write_text(json.dumps({"tags": tags, "bit_rate": br, "duration": 200.0}))
    os.utime(path, (age, age))
    return path


def age_tree(p, age=OLD):
    for dp, dn, fn in os.walk(p):
        for x in dn + fn:
            os.utime(pathlib.Path(dp) / x, (age, age))
    os.utime(p, (age, age))


def fake_probe_video(p):
    try:
        d = json.loads(pathlib.Path(p).read_text().strip())
        d["size"] = pathlib.Path(p).stat().st_size
        return d
    except Exception:
        return {}


def fake_probe_audio(p):
    try:
        d = json.loads(pathlib.Path(p).read_text().strip())
    except Exception:
        return {}
    return {"duration": d["duration"], "bit_rate": d["bit_rate"],
            "size": pathlib.Path(p).stat().st_size, "width": 0, "height": 0,
            "fps": 0.0, "tags": d["tags"], "has_cover": False}


def run_(fresh=()):
    """age every intake entry (dirs included) past the 30-min guard, except
    the paths in `fresh`, then run one intake pass."""
    age_tree(INTAKE)
    now = time.time()
    for f in fresh:
        os.utime(f, (now, now))
    return I.run()


I.probe_video = fake_probe_video
I.probe_audio = fake_probe_audio
I.run_ffmpeg = lambda args: False


def snapshot(root):
    out = {}
    for dp, dn, fn in os.walk(root):
        for x in dn + fn:
            p = pathlib.Path(dp) / x
            st = p.stat()
            out[str(p)] = (p.is_dir(), st.st_size, int(st.st_mtime))
    return out


# ---------------------------------------------------------------------------
print("1. classification")
reset()
tv = INTAKE / "Some.Show.S02E05.German.1080p.WEB.h264-GRP"
vid(tv / "Some.Show.S02E05.German.1080p.WEB.h264-GRP.mkv")
vid(tv / "Sample" / "sample-grp.mkv", pad=0)
c = I.classify(tv)
check("SxxEyy -> tv", c["kind"], "tv")
check("tv show name parsed", c.get("show"), "Some Show")
check("tv season/episode", (c["episodes"][0]["season"], c["episodes"][0]["episode"]), (2, 5))
check("sample clip is ignored", len(c["episodes"]), 1)
mv_ = INTAKE / "A.Movie.Title.2019.German.DL.1080p.BluRay.x264-GRP"
vid(mv_ / "grp-amt-1080p.mkv")
c = I.classify(mv_)
check("year + video -> movie", (c["kind"], c.get("title"), c.get("year")), ("movie", "A Movie Title", 2019))
nomv = INTAKE / "Something.Without.A.Year.German.1080p"
vid(nomv / "x.mkv")
check("video without year -> ambiguous", (I.classify(nomv)["kind"], I.classify(nomv).get("reason")),
      ("ambiguous", "no-year"))
two = INTAKE / "Two.Videos.2011"
vid(two / "a.mkv")
vid(two / "b.mkv")
check("two feature videos -> ambiguous", I.classify(two).get("reason"), "multiple-videos")
yt = INTAKE / "Channel - clip [dQw4w9WgXcQ]"
vid(yt / "Channel - clip [dQw4w9WgXcQ].mp4")
check("YouTube-looking -> flagged ambiguous", I.classify(yt).get("reason"), "youtube")
mus = INTAKE / "Artist - Album (2001) FLAC"
aud(mus / "01.flac", "Album", "Artist", "One", 1)
check("audio-only -> music", I.classify(mus)["kind"], "music")
check("decide: identical", I.decide({"width": 1, "height": 1, "fps": 25, "duration": 10, "bit_rate": 5, "size": 9},
                                    {"width": 1, "height": 1, "fps": 25, "duration": 10, "bit_rate": 5, "size": 9}),
      "identical")

# ---------------------------------------------------------------------------
print("2. quality outcomes (end to end)")
base = dict(w=1280, h=720, fps=23.976, dur=6000.0, br=4_000_000)
cases = {
    "identical": (base, base, "duplicate"),
    "better":    (base, dict(base, w=1920, h=1080, br=9_000_000), "replaced"),
    "worse":     (dict(base, w=1920, h=1080, br=9_000_000), base, "duplicate"),
    "fps-25":    (base, dict(base, w=1920, h=1080, br=9_000_000, fps=25.0), "ambiguous"),
    "dur+5%":    (base, dict(base, w=1920, h=1080, br=9_000_000, dur=6300.0), "ambiguous"),
}
for name, (lib_p, new_p, want) in cases.items():
    reset()
    folder = MEDIA / "Movies" / "Probe Film (2010)"
    vid(folder / "Probe Film (2010).mkv", **lib_p)
    (folder / "Probe Film (2010).nfo").write_text("<movie/>")
    vid(INTAKE / "Probe.Film.2010.German.1080p.WEB-GRP" / "grp.mkv", **new_p)
    res = run_()
    dups = list((MEDIA / "Movies" / "_duplicates").rglob("*.mkv")) if (MEDIA / "Movies" / "_duplicates").exists() else []
    lib_now = fake_probe_video(folder / "Probe Film (2010).mkv")
    intake_left = (INTAKE / "Probe.Film.2010.German.1080p.WEB-GRP").exists()
    if want == "duplicate":
        check(f"{name}: intake copy -> _duplicates", (len(dups), intake_left), (1, False))
        check(f"{name}: library file untouched", lib_now["width"], lib_p["w"])
        check(f"{name}: dup layout <Title (Year)> - intake dup <date>/",
              dups[0].parent.name.startswith("Probe Film (2010) - intake dup "), True)
    elif want == "replaced":
        check(f"{name}: new file took the library name", lib_now["width"], new_p["w"])
        check(f"{name}: old library copy kept in _duplicates", fake_probe_video(dups[0])["width"], lib_p["w"])
        check(f"{name}: NFO sidecar intact", (folder / "Probe Film (2010).nfo").exists(), True)
        check(f"{name}: run_actions.replaced", res["run_actions"]["replaced"], 1)
    else:
        check(f"{name}: left in intake as ambiguous", (intake_left, len(dups), res["items"]["ambiguous"]), (True, 0, 1))
        check(f"{name}: library untouched", lib_now["width"], lib_p["w"])
reset()
vid(MEDIA / "Movies" / "Probe Film (2010)" / "Probe Film (2010).mkv", **base)
vid(INTAKE / "Probe.Film.2010.x" / "a.mkv", **base)
run_()
check("_duplicates/.ignore created", (MEDIA / "Movies" / "_duplicates" / ".ignore").exists(), True)
check(".plexignore lists _duplicates/",
      "_duplicates/" in (MEDIA / "Movies" / ".plexignore").read_text().splitlines(), True)

# TV duplicate layout + new episode into an existing show
reset()
show = MEDIA / "TV Shows" / "Some Show"
vid(show / "Season 02" / "Some Show - S02E05.mkv", **base)
vid(INTAKE / "Some.Show.S02E05.German.720p-GRP" / "some.show.s02e05.720p.mkv", **base)
vid(INTAKE / "Some.Show.S02E06.German.720p-GRP" / "Some.Show.S02E06.German.720p-GRP.mkv", **base)
res = run_()
check("tv dup -> TV Shows/_duplicates/<Show>/Season XX/<orig>",
      (MEDIA / "TV Shows" / "_duplicates" / "Some Show" / "Season 02" / "some.show.s02e05.720p.mkv").exists(), True)
check("new episode -> <Show>/Season 02/<Show> - S02E06.mkv",
      (show / "Season 02" / "Some Show - S02E06.mkv").exists(), True)
check("both intake folders cleaned", sorted(p.name for p in INTAKE.iterdir() if not p.name.startswith(".")), [])

# ---------------------------------------------------------------------------
print("3. two-step replace ordering + mid-failure")
reset()
lib = vid(MEDIA / "Movies" / "Probe Film (2010)" / "Probe Film (2010).mkv", **base)
new = vid(INTAKE / "Probe.Film.2010.x" / "a.mkv", **dict(base, w=1920, h=1080, br=9_000_000))
p = I.Plan(INTAKE / "Probe.Film.2010.x")
I.plan_movie(p, I.classify(INTAKE / "Probe.Film.2010.x"))
g = p.groups[0]
check("replace group has 2 steps", len(g["moves"]), 2)
check("step 1 displaces the LIBRARY copy into _duplicates",
      (g["moves"][0]["src"] == str(lib), "/_duplicates/" in g["moves"][0]["dst"]), (True, True))
check("step 2 brings the intake file to the library name",
      (g["moves"][1]["src"], g["moves"][1]["dst"]), (str(new), str(lib)))
calls = []


def flaky_mv(src, dst):
    calls.append((str(src), str(dst)))
    if len(calls) == 2:          # step 2 fails
        return False
    return C.atomic_mv(src, dst)


out = organize.apply_group(g, dry_run=False, mv=flaky_mv)
check("mid-failure -> group reported failed", out, "failed")
check("rollback moved the library copy back", (lib.exists(), fake_probe_video(lib)["width"]), (True, 1280))
check("intake file untouched after rollback", new.exists(), True)
check("rollback was the 3rd call, dst->src of step 1", calls[2], (g["moves"][0]["dst"], g["moves"][0]["src"]))
calls.clear()


def dead_mv(src, dst):
    calls.append(1)
    return len(calls) == 1       # step 1 ok, step 2 fails, rollback fails


check("rollback failure -> rollback-failed (nothing deleted)",
      organize.apply_group(g, dry_run=False, mv=dead_mv), "rollback-failed")

# ---------------------------------------------------------------------------
print("4. EXDEV refusal")
reset()
a = vid(INTAKE / "x.mkv")
real_same = C.same_filesystem
C.same_filesystem = lambda x, y: False
check("atomic_mv refuses cross-device", C.atomic_mv(a, MEDIA / "Movies" / "x.mkv"), False)
check("source kept after EXDEV refusal", a.exists(), True)
res = run_()
check("run() preflight aborts on two mounts", res["abort_reason"], "preflight")
C.same_filesystem = real_same
check("atomic_mv never overwrites", C.atomic_mv(a, a), False)

# ---------------------------------------------------------------------------
print("5. incomplete-download guard")
reset()
rar = INTAKE / "Rar.Film.2012.German"
vid(rar / "rar.film.part1.rar")
vid(rar / "rar.film.mkv")
recent = INTAKE / "Fresh.Film.2013.German"
vid(recent / "fresh.mkv")
res = run_(fresh=[recent / "fresh.mkv"])
check(".rar -> pending, not moved", (rar.exists(), res["items"]["pending"] >= 1), (True, True))
check("mtime < 30 min -> pending, not moved", recent.exists(), True)
check("nothing reached the library", list((MEDIA / "Movies").iterdir()), [])

reset()
(INTAKE / "Empty.Pkg" / "sub").mkdir(parents=True)
res = run_()
check("empty leftover folder removed (rmdir only)", ((INTAKE / "Empty.Pkg").exists(), res["run_actions"]["cleaned"]), (False, 1))

# ---------------------------------------------------------------------------
print("6. `?` in titles")
check("assert_safe_target accepts `?`", C.assert_safe_target(INTAKE / "What?.2014") is None, True)
try:
    C.assert_safe_target(INTAKE / "glob*")
    check("assert_safe_target still refuses `*`", False, True)
except SystemExit:
    check("assert_safe_target still refuses `*`", True, True)
check("sanitize_name drops ? and maps :", C.sanitize_name('What?: A "Title"'), "What - A Title")
reset()
vid(MEDIA / "Movies" / "Why Not (2014)" / "Why Not (2014).mkv", **base)
vid(INTAKE / "Why.Not?.2014.German.720p" / "why.mkv", **base)
res = run_()
check("item with `?` is processed (duplicate)", res["run_actions"]["duplicate"], 1)

# ---------------------------------------------------------------------------
print("7. dry-run immutability")
reset()
vid(MEDIA / "Movies" / "Probe Film (2010)" / "Probe Film (2010).mkv", **base)
vid(INTAKE / "Probe.Film.2010.x" / "a.mkv", **dict(base, w=1920, h=1080, br=9_000_000))
vid(INTAKE / "Probe.Film.2010.y" / "a.mkv", **base)
age_tree(INTAKE)
before = snapshot(SHARE)
I.APPLY = False
res = I.run()
I.APPLY = True
check("dry run plans items", res["items"]["planned"], 2)
check("dry run changes NOTHING on disk (incl. no state file)", snapshot(SHARE), before)

# ---------------------------------------------------------------------------
print("8. cleanup refusals")
reset()
d = INTAKE / "Leftover"
vid(d / "junk.nfo")
check("cleanup refuses when a destination is missing",
      CL.cleanup(d, [str(MEDIA / "Movies" / "nope.mkv")]), False)
check("folder still there", d.exists(), True)
vid(d / "feature.mkv", pad=CL.SAMPLE_MAX_BYTES + 1)
dest = vid(MEDIA / "Movies" / "Z (2000)" / "Z (2000).mkv")
check("cleanup(guard_media) refuses while a feature video is left", CL.cleanup(d, [str(dest)], guard_media=True), False)
(d / "feature.mkv").unlink()
aud(d / "t.mp3", "A", "B", "C", 1)
check("cleanup(guard_media) refuses while audio is left", CL.cleanup(d, [str(dest)], guard_media=True), False)
(d / "t.mp3").unlink()
check("cleanup removes junk-only folder after verify", CL.cleanup(d, [str(dest)], guard_media=True), True)
check("cleanup refuses the intake root", CL.cleanup(INTAKE, [str(dest)]), False)
check("intake root survives", INTAKE.exists(), True)

# ---------------------------------------------------------------------------
print("9. safety stop: > MAX_ITEMS")
reset()
I.MAX_ITEMS = 3
for n in range(4):
    vid(MEDIA / "Movies" / f"Bulk {n} (2001)" / f"Bulk {n} (2001).mkv", **base)
    vid(INTAKE / f"Bulk.{n}.2001.German" / "b.mkv", **base)
res = run_()
check("run aborted", res["abort_reason"], "too-many-items")
check("zero moves", res["run_actions"].get("duplicate", 0), 0)
check("all 4 still in intake", len([p for p in INTAKE.iterdir() if not p.name.startswith(".")]), 4)

# ---------------------------------------------------------------------------
print("10. music")
reset()
alb = INTAKE / "Artist.-.Album.2001.FLAC"
aud(alb / "CD1" / "a.flac", "Album", "Artist", "One", 1)
aud(alb / "CD2" / "b.flac", "Album", "Artist", "Two", 1)
(alb / "cover.jpg").write_bytes(b"\xff\xd8x")
age_tree(alb)
res = run_()
tgt = MEDIA / "Music" / "Artist" / "Album (2001)"
check("multi-disc -> D-NN - Title", sorted(p.name for p in tgt.iterdir()),
      ["1-01 - One.flac", "2-01 - Two.flac", "album.nfo", "folder.jpg"])
reset()
alb = INTAKE / "Mixed"
aud(alb / "a.mp3", "Album", "Artist", "One", 1)
aud(alb / "b.mp3", "Other", "Artist", "Two", 2)
run_()
check("inconsistent album tags -> left as ambiguous", alb.exists(), True)

# ---------------------------------------------------------------------------
print("11. metrics + rescan scope")
reset()
vid(INTAKE / "No.Year.Here" / "x.mkv")
I.push_metrics(I.render_metrics(run_()))
prom = (TMP / "metrics.prom").read_text()
check("metrics: ambiguous gauge", 'media_intake_items{state="ambiguous"} 1' in prom, True)
check("metrics: failed gauge present", 'media_intake_items{state="failed"} 0' in prom, True)
check("metrics carry no item names", "No.Year" in prom or "No Year" in prom, False)
src = (SCRIPTS / "rescan.py").read_text()
check("rescan.py has no /Library/Refresh call", "/Library/Refresh\"" in src or "/Library/Refresh'" in src
      or 'Library/Refresh",' in src, False)
check("rescan: Plex section refresh is path-scoped", "/refresh?path=" in src, True)
check("rescan: no paths -> no calls", R.rescan_paths([], env={}), {"plex": 0, "jellyfin": 0})
check("rescan: longest section match", R.pick_section("/data/data/Movies/X (1)",
      [("1", "/data/data"), ("4", "/data/data/Movies")]), "4")
check("rescan: jellyfin path map", R.map_path("/data/data/Movies/X", "/data/=/media/"), "/media/data/Movies/X")

# ---------------------------------------------------------------------------
print("12. manifests")
docs = {}
for f in APPDIR.glob("*cronjob.yaml"):
    for d in yaml.safe_load_all(f.read_text()):
        if d and d.get("kind") == "CronJob":
            docs[d["metadata"]["name"]] = d
w = docs.get("media-intake-watcher")
check("media-intake-watcher CronJob exists", w is not None, True)
if w:
    spec = w["spec"]
    pod = spec["jobTemplate"]["spec"]["template"]["spec"]
    claims = [v["persistentVolumeClaim"]["claimName"] for v in pod["volumes"] if "persistentVolumeClaim" in v]
    check("watcher: every 30 min", spec["schedule"], "*/30 * * * *")
    check("watcher: concurrencyPolicy Forbid", spec["concurrencyPolicy"], "Forbid")
    check("watcher: ONE share-root mount", claims, ["plex-media-smb"])
    check("watcher: ttlSecondsAfterFinished", "ttlSecondsAfterFinished" in spec["jobTemplate"]["spec"], True)
    env = {e["name"]: e.get("value") for e in pod["containers"][0]["env"]}
    check("watcher: kill switch INTAKE_APPLY present", "INTAKE_APPLY" in env, True)
    check("watcher: ffprobe from pinned image volume",
          any("image" in v and "@sha256:" in v["image"]["reference"] for v in pod["volumes"]), True)
for name in ("media-organize", "media-cleanup"):
    pod = docs[name]["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    claims = [v["persistentVolumeClaim"]["claimName"] for v in pod["volumes"] if "persistentVolumeClaim" in v]
    check(f"{name}: single share-root mount (no EXDEV)", claims, ["plex-media-smb"])
for name, d in sorted(docs.items()):
    if d["spec"].get("suspend"):
        check(f"{name}: templated job has a TTL", "ttlSecondsAfterFinished" in d["spec"]["jobTemplate"]["spec"], True)
rule = yaml.safe_load((REPO / "kubernetes/apps/monitoring/kube-prometheus-stack/app/media-intake-alerts.yaml").read_text())
check("alert rule: release label", rule["metadata"]["labels"].get("release"), "kube-prometheus-stack")
exprs = " ".join(r["expr"] for g in rule["spec"]["groups"] for r in g["rules"])
check("alert rule: has absent() guard", "absent(media_intake_" in exprs, True)
check("alert rule: ambiguous > 24h", "86400" in exprs or "24" in exprs, True)
ks = (REPO / "kubernetes/apps/monitoring/kube-prometheus-stack/app/kustomization.yaml").read_text()
check("alert rule listed in kustomization", "./media-intake-alerts.yaml" in ks, True)

# ---------------------------------------------------------------------------
print("13. daily digest (OpenClaw briefing payload)")
import importlib.util  # noqa: E402
spec = importlib.util.spec_from_file_location("digest", REPO / "runbooks/media-intake-digest.py")
dg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dg)
sample = prom.replace("media_intake_items{", 'media_intake_items{job="media-intake-watcher",')
payload = dg.build(dg.parse(sample), "2026-09-28")
check("digest: kind/source/severity/action",
      (payload["kind"], payload["source"], payload["severity"], payload["action"]),
      ("window_warning", "maintenance", "info", "ack"))
check("digest: key is date-scoped", payload["key"], "media-intake-2026-09-28")
check("digest: reports ambiguous count", "1 ambiguous" in payload["title"], True)
check("digest: no metrics -> None", dg.build({}, "x"), None)

shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
