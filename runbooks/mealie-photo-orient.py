#!/usr/bin/env python3
"""Work out how far each recipe card's picture side has to be turned to sit upright.

The cards were fed through the scanner in whatever orientation was convenient, so
about a third of the picture sides come out sideways or upside down. The PDFs carry
no `/Rotate` metadata, so the orientation has to be derived from the page content.

**Page shape is not the answer.** Two-person cards are genuinely portrait while the
standard cards are landscape, so "portrait" says nothing about whether a scan is
wrong -- 66 of 159 photo pages are portrait and most of them are perfectly upright.

What works is tesseract's orientation detection (`--psm 0`), with one caveat that
matters: these pages are mostly photograph with a single line of title text, so OSD
confidence is often below 1.0 and it is sometimes wrong or silent. It is a strong
first pass, not an oracle. Run `review` afterwards to eyeball the ones it wants to
change, and record any disagreement in the overrides file -- on the first run 46 of
159 needed rotating and 10 of those needed correcting by eye.

Writes `<out-dir>/rotation.json`, which `mealie-import.py images` consumes.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# tesseract reports how far to turn the image CLOCKWISE to correct it, which is the
# same convention `sips -r` and this file's rotation.json use throughout.
OSD_DPI = 150


def photo_page(content_page: int) -> int:
    """Cards are scanned in pairs, so the picture side is the other page."""
    return content_page + 1 if content_page % 2 else content_page - 1


def detect(pdf: Path, page: int) -> tuple:
    """(degrees clockwise, confidence). Confidence 0 means tesseract had no opinion.

    Both hops have a trap. pdftoppm only writes to stdout when NO output-file root
    is given -- passing "-" makes it a filename root and it writes nothing. And
    tesseract cannot take this image on stdin ("Error during processing"), so the
    render has to land in a real file first. Silent zeros from either look exactly
    like "every page is already upright".
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "page")
        subprocess.run(
            ["pdftoppm", "-jpeg", "-r", str(OSD_DPI), "-f", str(page), "-l", str(page),
             "-singlefile", str(pdf), root],
            capture_output=True, check=True,
        )
        proc = subprocess.run(
            ["tesseract", root + ".jpg", "-", "--psm", "0"], capture_output=True,
        )
    out = proc.stdout.decode(errors="replace")
    rotate = re.search(r"Rotate:\s*(\d+)", out)
    conf = re.search(r"Orientation confidence:\s*([\d.]+)", out)
    return (int(rotate.group(1)) if rotate else 0,
            float(conf.group(1)) if conf else 0.0)


def load_keys(out_dir: Path) -> list:
    extractions = json.loads((out_dir / "extractions.json").read_text())
    return [
        {"key": r["key"], "doc": str(r["paperless_doc_id"]),
         "photo_page": photo_page(r["paperless_page"])}
        for r in extractions
    ]


def cmd_detect(args):
    out_dir = Path(args.out_dir).expanduser()
    overrides = {}
    if args.overrides and Path(args.overrides).expanduser().exists():
        overrides = {k: int(v) for k, v in
                     json.loads(Path(args.overrides).expanduser().read_text()).items()}

    entries = load_keys(out_dir)

    def work(entry):
        rotate, conf = detect(out_dir / "pdfs" / f"{entry['doc']}.pdf", entry["photo_page"])
        return {**entry, "osd_rotate": rotate, "confidence": round(conf, 2)}

    with ThreadPoolExecutor(args.jobs) as pool:
        results = list(pool.map(work, entries))

    rotation, overridden = {}, 0
    for r in results:
        if r["key"] in overrides:
            r["final"] = overrides[r["key"]]
            overridden += 1
        else:
            r["final"] = r["osd_rotate"]
        if r["final"]:
            rotation[r["key"]] = r["final"]

    (out_dir / "rotation.json").write_text(json.dumps(rotation, indent=1, sort_keys=True))
    (out_dir / "rotation-detail.json").write_text(json.dumps(results, indent=1))

    counts = {}
    for r in results:
        counts[r["final"]] = counts.get(r["final"], 0) + 1
    print(f"pages examined     : {len(results)}")
    print(f"rotations applied  : {counts}")
    print(f"from overrides     : {overridden}")
    unsure = [r["key"] for r in results
              if r["final"] and r["key"] not in overrides and r["confidence"] < 1.0]
    print(f"low-confidence     : {len(unsure)} -> review these first: {unsure[:12]}")
    print(f"written            : {out_dir / 'rotation.json'}")
    return 0


def cmd_review(args):
    """Render contact sheets of the corrected photos so the result can be eyeballed.

    Reviewing the OUTPUT rather than the input is the point: a wrong rotation is
    instantly obvious in a grid and invisible in a confidence score.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        sys.exit(
            "review needs Pillow: python3 -m venv .venv && .venv/bin/pip install Pillow\n"
            "(detect does not need it -- only the contact sheets do)"
        )
    out_dir = Path(args.out_dir).expanduser()
    rotation = json.loads((out_dir / "rotation.json").read_text())
    entries = load_keys(out_dir)
    if args.changed_only:
        entries = [e for e in entries if e["key"] in rotation]
    entries.sort(key=lambda e: (int(e["doc"]), e["key"]))

    sheets_dir = out_dir / "orientation-sheets"
    sheets_dir.mkdir(exist_ok=True)
    cell, cols, rows = 200, 5, 4
    per_sheet = cols * rows

    for index in range(0, len(entries), per_sheet):
        chunk = entries[index:index + per_sheet]
        sheet = Image.new("RGB", (cols * cell, rows * (cell + 14)), "white")
        draw = ImageDraw.Draw(sheet)
        for i, entry in enumerate(chunk):
            render = subprocess.run(
                ["pdftoppm", "-jpeg", "-r", "40", "-f", str(entry["photo_page"]),
                 "-l", str(entry["photo_page"]), "-singlefile",
                 str(out_dir / "pdfs" / f"{entry['doc']}.pdf")],
                capture_output=True,
            )
            tmp = sheets_dir / "_tmp.jpg"
            tmp.write_bytes(render.stdout)
            img = Image.open(tmp)
            degrees = rotation.get(entry["key"], 0)
            if degrees:
                img = img.rotate(-degrees, expand=True)   # PIL turns anticlockwise
            img.thumbnail((cell - 8, cell - 8))
            x, y = (i % cols) * cell, (i // cols) * (cell + 14)
            sheet.paste(img, (x + 4, y + 14 + (cell - 8 - img.height) // 2))
            draw.text((x + 3, y + 2), f"{entry['key']} r{degrees}", fill="black")
            draw.rectangle([x, y, x + cell - 1, y + cell + 13], outline="#bbbbbb")
        sheet.save(sheets_dir / f"sheet-{index // per_sheet:02d}.jpg", quality=70)
    (sheets_dir / "_tmp.jpg").unlink(missing_ok=True)
    print(f"contact sheets in {sheets_dir}")
    print("Anything still sideways or upside down goes in the overrides file as")
    print('  {"<key>": <degrees clockwise>}   then re-run `detect --overrides`.')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="~/.cache/mealie-import")
    sub = parser.add_subparsers(dest="command", required=True)
    detect_cmd = sub.add_parser("detect", help="detect orientation, write rotation.json")
    detect_cmd.add_argument("--overrides", help="JSON of key -> degrees that wins over OSD")
    detect_cmd.add_argument("--jobs", type=int, default=6)
    review = sub.add_parser("review", help="render contact sheets of the corrected photos")
    review.add_argument("--changed-only", action="store_true",
                        help="only pages this run would rotate")
    args = parser.parse_args()
    return {"detect": cmd_detect, "review": cmd_review}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
