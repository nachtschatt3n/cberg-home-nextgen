#!/usr/bin/env python3
"""Import the household's scanned recipe cards from Paperless-ngx into Mealie.

Why this exists instead of Mealie's built-in AI importer
--------------------------------------------------------
Mealie can import a recipe by handing text to an LLM (`POST /api/recipes/create/ai`).
Benchmarked against the local Ollama (`gemma4:26b`) on 2026-08-24 that path cost
**9m53s for a single card** (~25h for the corpus, saturating a shared host) and
still produced unusable output: all 16 ingredients landed in a single unstructured
`note` field, `recipeServings` was 0, and no tags carried across.

The reason is not the model, it is the *input*. Paperless' flattened `content`
field destroys the card's geometry:

    Hahnchen 1100g 1500g 1.500g          <- 2P / 3P / 4P columns, collapsed

`pdftotext -layout` keeps those columns apart, so this script re-extracts from the
archived PDF instead of reusing `content`. Extraction here is deterministic and
instant; the semantic parse is done downstream by agents that receive
layout-preserved text (see `runbooks/mealie-import.md`).

PRIVACY
-------
Recipe bodies are Paperless document *content*. Per `docs/sops/paperless.md` §10 and
the repository's public-repo rule they must never be committed. `extract` therefore
refuses to write its output anywhere inside the git repository -- the guard is in
`_assert_outside_repo()`, not merely a convention.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# --- corpus definition -------------------------------------------------------
# The recipe corpus is `document_type=12` (equivalently tag 38 "Food") -> 154 docs.
# It is deliberately NOT the "Recipe" tag 51: that returns 147 and silently drops
# 7 genuine cards that were never tagged. Verified 2026-08-24.
DOCUMENT_TYPE_ID = 12

# A scanned card is two PDF pages: one photo side, one content side. The content
# side is text-dense, the photo side yields only sparse mirrored fragments. A
# document may hold several cards (4- and 6-page scans are 2 and 3 recipes), so
# recipes are counted per content page, never per document.
CONTENT_PAGE_MIN_CHARS = 1000

# OCR of these cards drops the `ff`/`fl` ligatures outright, consistently enough
# to repair by table. Applied to extracted text before anything else reads it.
LIGATURE_REPAIRS = [
    ("Karto eln", "Kartoffeln"),
    ("Pfe er", "Pfeffer"),
    ("Sonnen ocken", "Sonnenflocken"),
    ("Son en ocken", "Sonnenflocken"),
    ("Son enblumenkerne", "Sonnenblumenkerne"),
    ("Au au orm", "Auflaufform"),
    ("durch ießt", "durchfließt"),
    ("bissfest", "bissfest"),
    ("Essig*", "Essig*"),
]

# Paperless titles are dish names for most of the corpus, but scans that were
# never post-processed keep their camera filename. Those must fall back to a
# title read off the card itself.
GENERIC_TITLE_RE = re.compile(r"^\d{8}[_-]\d{6}$|^(scan|img|dokument|document)[_ -]?\d*$", re.I)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _assert_outside_repo(path: Path) -> None:
    """Refuse to write recipe content anywhere git tracks.

    This is a hard guard rather than a comment because the failure is silent and
    permanent: the repository is public, and a committed recipe body cannot be
    un-published by deleting it later.
    """
    resolved = path.resolve()
    try:
        resolved.relative_to(_repo_root())
    except ValueError:
        return
    sys.exit(
        f"refusing to write recipe content inside the repository: {resolved}\n"
        "Recipe bodies are Paperless document content and must stay out of git "
        "(docs/sops/paperless.md). Pass --out-dir with a path outside the repo."
    )


# --- Paperless ---------------------------------------------------------------

def _paperless_get(base: str, token: str, path: str) -> dict:
    req = urllib.request.Request(
        f"{base}{path}", headers={"Authorization": f"Token {token}"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def fetch_documents(base: str, token: str) -> list:
    """All recipe documents, metadata only -- `content` is ignored on purpose."""
    docs = []
    path = f"/api/documents/?document_type__id={DOCUMENT_TYPE_ID}&page_size=100&ordering=id"
    while path:
        page = _paperless_get(base, token, path)
        docs += page["results"]
        nxt = page.get("next")
        path = nxt[len(base):] if nxt and nxt.startswith(base) else _relative(nxt)
    return docs


def _relative(url):
    if not url:
        return None
    return "/" + url.split("/", 3)[3] if url.startswith("http") else url


def fetch_lookup(base: str, token: str, endpoint: str) -> dict:
    data = _paperless_get(base, token, f"/api/{endpoint}/?page_size=200")
    return {x["id"]: x["name"] for x in data["results"]}


def download_pdf(base: str, token: str, doc_id: int, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 1000:
        return
    req = urllib.request.Request(
        f"{base}/api/documents/{doc_id}/download/",
        headers={"Authorization": f"Token {token}"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        dest.write_bytes(resp.read())


# --- PDF text extraction -----------------------------------------------------

def _pdf_page_count(pdf: Path) -> int:
    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
    m = re.search(r"^Pages:\s+(\d+)", out, re.M)
    if not m:
        raise RuntimeError(f"cannot read page count from {pdf}")
    return int(m.group(1))


def _page_text(pdf: Path, page: int) -> str:
    """Layout-preserving text for one page.

    `-layout` is what keeps the 2P/3P/4P quantity columns in separate character
    ranges; plain extraction (and Paperless' own `content`) collapses them.
    """
    return subprocess.run(
        ["pdftotext", "-layout", "-f", str(page), "-l", str(page), str(pdf), "-"],
        capture_output=True,
        text=True,
    ).stdout


def repair_text(text: str) -> str:
    for broken, fixed in LIGATURE_REPAIRS:
        text = text.replace(broken, fixed)
    return text


def detect_family(text: str) -> str:
    """Which card layout this is. Three exist in the corpus, and they need
    different reading strategies downstream, so the family travels with the text."""
    if re.search(r"\b\d\s*[pP]\b\s+\d\s*[pP]\b", text):
        # HelloFresh: ingredient table with one quantity column per serving size
        return "A-multiserving"
    if re.search(r"Zutaten\s*\n?\s*\d\s*Personen|alle Zutaten", text):
        # 2-person card, quantities inline, "for 4 double everything"
        return "B-2person"
    # Marley Spoon style: bullet lists under "Was du von uns bekommst"
    return "C-bulletlist"


def extract_document(pdf: Path, doc: dict, tags: dict, correspondents: dict) -> list:
    """Split one scanned document into its constituent recipes."""
    n_pages = _pdf_page_count(pdf)
    recipes = []
    for page in range(1, n_pages + 1):
        text = repair_text(_page_text(pdf, page))
        if len(re.sub(r"\s", "", text)) <= CONTENT_PAGE_MIN_CHARS:
            continue  # photo side
        recipes.append(
            {
                "key": f"{doc['id']}-p{page}",
                "paperless_doc_id": doc["id"],
                "paperless_page": page,
                "family": detect_family(text),
                # Only a real dish name is passed through; a camera filename would
                # otherwise become the recipe title.
                "paperless_title": None
                if GENERIC_TITLE_RE.match(doc["title"].strip())
                else doc["title"].strip(),
                "source": correspondents.get(doc.get("correspondent"), "unknown"),
                "tags": [tags[t] for t in doc.get("tags", []) if t in tags],
                "layout_text": text,
            }
        )

    # A document holding N cards must yield exactly N content pages. If that
    # invariant breaks, a recipe was silently dropped or a photo page was
    # mistaken for content -- both produce a quietly incomplete import, which is
    # far worse than a loud failure.
    expected = n_pages // 2
    if len(recipes) != expected:
        raise RuntimeError(
            f"doc {doc['id']}: {n_pages} pages implies {expected} recipes but "
            f"{len(recipes)} content pages were detected"
        )
    return recipes


# --- Mealie ------------------------------------------------------------------

def _mealie(method: str, url: str, token: str, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=300) as resp:
        body = resp.read().decode()
        return json.loads(body) if body else None


def imported_keys(base: str, token: str) -> set:
    """Keys already in Mealie, read back from each recipe's `extras`.

    This is what makes the import resumable: a re-run must skip what landed
    rather than create a second copy of every recipe.
    """
    keys = set()
    page = 1
    while True:
        data = _mealie(
            "GET", f"{base}/api/recipes?page={page}&perPage=100", token
        )
        for item in data.get("items", []):
            full = _mealie("GET", f"{base}/api/recipes/{item['slug']}", token)
            key = (full.get("extras") or {}).get("paperless_key")
            if key:
                keys.add(key)
        if page >= data.get("total_pages", 1):
            break
        page += 1
    return keys


def _fetch_all(base: str, token: str, path: str) -> dict:
    """normalised name -> id for an organizer collection."""
    found, page = {}, 1
    while True:
        data = _mealie("GET", f"{base}/{path}?page={page}&perPage=100", token)
        for item in data.get("items", []):
            found[_norm(item["name"])] = item["id"]
        if page >= data.get("total_pages", 1):
            break
        page += 1
    return found


def _norm(name: str) -> str:
    """Match Mealie's own uniqueness rule.

    Mealie stores a `name_normalized` column that is lower-cased and stripped of
    diacritics, and the unique constraint is on that. A cache keyed on plain
    lower-case therefore misses `Crème fraîche` when `creme fraiche` already
    exists, and the create then fails.
    """
    decomposed = unicodedata.normalize("NFKD", name.strip().casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


class OrganizerCache:
    """Resolves every organizer a recipe references to an existing ID.

    Units, foods, tags and categories must all exist before a recipe can
    reference them:

      - `unit`/`food` are advertised in the OpenAPI as accepting a create-shape
        carrying only a name, but the update handler rejects that with
        `ValueError: Expected 'id' to be provided for unit`.
      - `tags`/`recipeCategory` fail more confusingly. Passing name+slug makes
        Mealie try to create them, and when one already exists the unique
        violation surfaces as `400 Recipe already exists` -- an error about the
        recipe, naming the wrong object entirely. That message cost real time to
        trace, hence this note.

    Resolving up-front also stops the corpus sprouting near-duplicate foods.
    """

    KINDS = {
        "units": "api/units",
        "foods": "api/foods",
        "tags": "api/organizers/tags",
        "categories": "api/organizers/categories",
    }

    def __init__(self, base: str, token: str):
        self.base, self.token = base, token
        self.cache = {k: _fetch_all(base, token, path) for k, path in self.KINDS.items()}

    def _resolve(self, kind: str, name: str) -> dict:
        cache, key = self.cache[kind], _norm(name)
        if key not in cache:
            try:
                cache[key] = _mealie(
                    "POST", f"{self.base}/{self.KINDS[kind]}", self.token,
                    {"name": name.strip()},
                )["id"]
            except urllib.error.HTTPError as exc:
                # 409 means another name normalises to the same key -- re-read the
                # collection and use what is already there rather than failing.
                if exc.code != 409:
                    raise
                self.cache[kind] = _fetch_all(self.base, self.token, self.KINDS[kind])
                cache = self.cache[kind]
                if key not in cache:
                    raise
        return {"id": cache[key], "name": name.strip()}

    def apply(self, recipe: dict) -> dict:
        for ing in recipe.get("recipeIngredient") or []:
            for field, kind in (("unit", "units"), ("food", "foods")):
                value = ing.get(field)
                if isinstance(value, dict) and value.get("name") and not value.get("id"):
                    ing[field] = self._resolve(kind, value["name"])
        for field, kind in (("tags", "tags"), ("recipeCategory", "categories")):
            items = recipe.get(field) or []
            resolved = []
            for item in items:
                name = item.get("name") if isinstance(item, dict) else item
                if not name:
                    continue
                entry = self._resolve(kind, name)
                # the recipe payload wants a slug alongside the id
                entry["slug"] = _norm(name).replace(" ", "-").replace(",", "")
                resolved.append(entry)
            if items:
                recipe[field] = resolved
        return recipe


def push_recipe(base: str, token: str, recipe: dict, organizers: OrganizerCache) -> str:
    """Create one recipe, then fill it in.

    Mealie's create endpoint only accepts a name; everything else has to go in a
    follow-up PUT against the returned slug. If that PUT fails the shell recipe is
    removed again -- leaving it behind would occupy the slug and, worse, count as
    an imported recipe while holding none of its content.
    """
    recipe = organizers.apply(recipe)
    slug = _mealie("POST", f"{base}/api/recipes", token, {"name": recipe["name"]})
    try:
        current = _mealie("GET", f"{base}/api/recipes/{slug}", token)
        current.update({k: v for k, v in recipe.items() if k != "name"})
        current["extras"] = {**(current.get("extras") or {}), **recipe.get("extras", {})}
        _mealie("PUT", f"{base}/api/recipes/{slug}", token, current)
    except Exception:
        try:
            _mealie("DELETE", f"{base}/api/recipes/{slug}", token)
        except Exception:
            pass
        raise
    return slug


# --- commands ----------------------------------------------------------------

def cmd_extract(args):
    out_dir = Path(args.out_dir).expanduser()
    _assert_outside_repo(out_dir)
    (out_dir / "pdfs").mkdir(parents=True, exist_ok=True)

    base, token = args.paperless_url.rstrip("/"), os.environ["PAPERLESS_TOKEN"]
    docs = fetch_documents(base, token)
    tags = fetch_lookup(base, token, "tags")
    correspondents = fetch_lookup(base, token, "correspondents")
    print(f"documents: {len(docs)}")

    with ThreadPoolExecutor(6) as pool:
        list(pool.map(
            lambda d: download_pdf(base, token, d["id"], out_dir / "pdfs" / f"{d['id']}.pdf"),
            docs,
        ))

    recipes, failures = [], []
    for doc in docs:
        try:
            recipes += extract_document(
                out_dir / "pdfs" / f"{doc['id']}.pdf", doc, tags, correspondents
            )
        except RuntimeError as exc:
            failures.append(str(exc))

    dest = out_dir / "extractions.json"
    dest.write_text(json.dumps(recipes, ensure_ascii=False, indent=1))
    dest.chmod(0o600)

    families = {}
    for r in recipes:
        families[r["family"]] = families.get(r["family"], 0) + 1
    print(f"recipes extracted: {len(recipes)}")
    print(f"layout families  : {families}")
    print(f"needing a title from the card: "
          f"{sum(1 for r in recipes if not r['paperless_title'])}")
    print(f"written: {dest}")
    if failures:
        print(f"\nFAILED ({len(failures)}):")
        for f in failures:
            print(f"  {f}")
        return 1
    return 0


def cmd_push(args):
    base, token = args.mealie_url.rstrip("/"), os.environ["MEALIE_TOKEN"]
    recipes = json.loads(Path(args.recipes).expanduser().read_text())
    done = imported_keys(base, token) if not args.no_resume else set()
    print(f"already imported: {len(done)}")
    organizers = OrganizerCache(base, token)

    created, skipped, failed = 0, 0, []
    for recipe in recipes:
        key = recipe.get("extras", {}).get("paperless_key")
        if key in done:
            skipped += 1
            continue
        try:
            slug = push_recipe(base, token, recipe, organizers)
            created += 1
            print(f"  + {slug}")
        except (urllib.error.HTTPError, urllib.error.URLError, KeyError) as exc:
            failed.append((key, str(exc)))
    print(f"\ncreated={created} skipped={skipped} failed={len(failed)}")
    for key, err in failed:
        print(f"  FAIL {key}: {err}")
    return 1 if failed else 0


def _photo_page(content_page: int) -> int:
    """The picture side that belongs to a given content side.

    Cards are scanned in fixed pairs -- (1,2), (3,4), (5,6) -- with the photo and
    the method on opposite sides of the same card. So the photo for an odd content
    page is the page after it, and for an even content page the page before it.
    """
    return content_page + 1 if content_page % 2 else content_page - 1


def cmd_images(args):
    """Attach each recipe's own photo, rendered from the picture side of its scan.

    Done as a separate pass keyed on `extras.paperless_key` rather than during
    `push`, so it can be re-run for recipes that failed without touching the ones
    that succeeded.
    """
    base, token = args.mealie_url.rstrip("/"), os.environ["MEALIE_TOKEN"]
    pdf_dir = Path(args.out_dir).expanduser() / "pdfs"

    attached, skipped, failed = 0, 0, []
    page_num = 1
    while True:
        data = _mealie("GET", f"{base}/api/recipes?page={page_num}&perPage=100", token)
        for item in data.get("items", []):
            full = _mealie("GET", f"{base}/api/recipes/{item['slug']}", token)
            extras = full.get("extras") or {}
            key = extras.get("paperless_key")
            if not key:
                continue
            if full.get("image") and not args.force:
                skipped += 1
                continue
            doc_id, content_page = key.split("-p")
            pdf = pdf_dir / f"{doc_id}.pdf"
            try:
                jpeg = _render_page(pdf, _photo_page(int(content_page)))
                _upload_image(base, token, item["slug"], jpeg)
                attached += 1
                print(f"  * {item['slug']}")
            except Exception as exc:  # noqa: BLE001 - report, never abort the pass
                failed.append((key, str(exc)))
        if page_num >= data.get("total_pages", 1):
            break
        page_num += 1

    print(f"\nattached={attached} skipped={skipped} failed={len(failed)}")
    for key, err in failed:
        print(f"  FAIL {key}: {err}")
    return 1 if failed else 0


def _render_page(pdf: Path, page: int) -> bytes:
    """Render one PDF page to JPEG at a resolution worth looking at."""
    result = subprocess.run(
        # pdftoppm writes the image to stdout only when no output-file root is
        # given; passing "-" makes it a filename root instead and writes nothing.
        ["pdftoppm", "-jpeg", "-r", "150", "-f", str(page), "-l", str(page),
         "-singlefile", str(pdf)],
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        raise RuntimeError(f"pdftoppm failed for {pdf} page {page}")
    return result.stdout


def _upload_image(base: str, token: str, slug: str, jpeg: bytes) -> None:
    boundary = "----mealieimport"
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; "
        f"filename=\"{slug}.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n".encode(),
        jpeg,
        f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"extension\""
        f"\r\n\r\njpg\r\n--{boundary}--\r\n".encode(),
    ]
    req = urllib.request.Request(
        f"{base}/api/recipes/{slug}/image", data=b"".join(parts), method="PUT"
    )
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    urllib.request.urlopen(req, timeout=300).read()


def cmd_cookbooks(args):
    """One cookbook per source brand.

    Mealie cookbooks are saved smart filters, not folders, so a brand cookbook is
    a query over the category the import already sets. That means it keeps itself
    up to date: a recipe imported later appears without touching the cookbook.
    """
    base, token = args.mealie_url.rstrip("/"), os.environ["MEALIE_TOKEN"]
    brands = {}
    page_num = 1
    while True:
        data = _mealie("GET", f"{base}/api/recipes?page={page_num}&perPage=100", token)
        for item in data.get("items", []):
            full = _mealie("GET", f"{base}/api/recipes/{item['slug']}", token)
            if not (full.get("extras") or {}).get("paperless_key"):
                continue
            for category in full.get("recipeCategory") or []:
                brands[category["name"]] = brands.get(category["name"], 0) + 1
        if page_num >= data.get("total_pages", 1):
            break
        page_num += 1

    existing = {
        c["name"]
        for c in _mealie("GET", f"{base}/api/households/cookbooks?perPage=100", token)["items"]
    }
    for brand, count in sorted(brands.items(), key=lambda kv: -kv[1]):
        if brand in existing:
            print(f"  = {brand} ({count} recipes, already exists)")
            continue
        _mealie(
            "POST",
            f"{base}/api/households/cookbooks",
            token,
            {
                "name": brand,
                "description": f"Recipe cards from {brand}",
                "public": False,
                "queryFilterString": f'recipeCategory.name = "{brand}"',
            },
        )
        print(f"  + {brand} ({count} recipes)")
    return 0


def cmd_correct(args):
    """Apply verification corrections onto recipes that are already imported.

    `push` deliberately skips anything already traceable to Paperless, which is
    what makes it safe to re-run -- so corrections need their own path. Input is
    a list of `{paperless_key, changes, recipe}` objects; only the named recipes
    are touched.
    """
    base, token = args.mealie_url.rstrip("/"), os.environ["MEALIE_TOKEN"]
    corrections = []
    for path in sorted(Path(args.corrections).expanduser().glob("*.json")) \
            if Path(args.corrections).expanduser().is_dir() \
            else [Path(args.corrections).expanduser()]:
        corrections += json.loads(path.read_text())
    print(f"corrections to apply: {len(corrections)}")

    # map paperless_key -> slug once, rather than re-scanning per correction
    by_key, page = {}, 1
    while True:
        data = _mealie("GET", f"{base}/api/recipes?page={page}&perPage=100", token)
        for item in data.get("items", []):
            full = _mealie("GET", f"{base}/api/recipes/{item['slug']}", token)
            key = (full.get("extras") or {}).get("paperless_key")
            if key:
                by_key[key] = item["slug"]
        if page >= data.get("total_pages", 1):
            break
        page += 1

    organizers = OrganizerCache(base, token)
    applied, missing, failed = 0, [], []
    for correction in corrections:
        key = correction.get("paperless_key")
        slug = by_key.get(key)
        if not slug:
            missing.append(key)
            continue
        try:
            recipe = organizers.apply(correction["recipe"])
            current = _mealie("GET", f"{base}/api/recipes/{slug}", token)
            live_name = current["name"]
            current.update({k: v for k, v in recipe.items() if k != "slug"})
            current["extras"] = {**(current.get("extras") or {}), **recipe.get("extras", {})}
            try:
                _mealie("PUT", f"{base}/api/recipes/{slug}", token, current)
            except urllib.error.HTTPError as exc:
                # The corpus holds a few dishes scanned twice, so Mealie stored the
                # second as "<name> (1)". A correction echoes back the un-suffixed
                # name, and renaming onto the sibling collides -- reported, as ever,
                # as "Recipe already exists". The title change is incidental there,
                # so fall back to the stored name. Corrections that genuinely fix a
                # title still succeed on the first attempt.
                if exc.code != 400 or current["name"] == live_name:
                    raise
                current["name"] = live_name
                _mealie("PUT", f"{base}/api/recipes/{slug}", token, current)
                print(f"  ! {key}: kept stored name {live_name!r} (rename collided)")
            applied += 1
            for change in correction.get("changes", []):
                print(f"  ~ {key}: {change}")
        except (urllib.error.HTTPError, urllib.error.URLError, KeyError) as exc:
            failed.append((key, str(exc)))

    print(f"\napplied={applied} not-found={len(missing)} failed={len(failed)}")
    for key in missing:
        print(f"  MISSING {key}")
    for key, err in failed:
        print(f"  FAIL {key}: {err}")
    return 1 if failed else 0


def cmd_status(args):
    base, token = args.mealie_url.rstrip("/"), os.environ["MEALIE_TOKEN"]
    done = imported_keys(base, token)
    total = _mealie("GET", f"{base}/api/recipes?perPage=1", token)["total"]
    print(f"recipes in Mealie      : {total}")
    print(f"traceable to Paperless : {len(done)}")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        default="~/.cache/mealie-import",
        help="where extracted recipe content is written (must be outside the repo)",
    )
    parser.add_argument("--paperless-url", default="http://127.0.0.1:8010")
    parser.add_argument("--mealie-url", default="http://127.0.0.1:9010")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("extract", help="split scans into per-recipe layout text")
    push = sub.add_parser("push", help="create recipes in Mealie from structured JSON")
    push.add_argument("recipes")
    push.add_argument("--no-resume", action="store_true",
                      help="do not skip recipes already traceable to Paperless")
    images = sub.add_parser("images", help="attach each recipe's photo from its scan")
    images.add_argument("--force", action="store_true",
                        help="replace images that are already set")
    sub.add_parser("cookbooks", help="create one smart cookbook per source brand")
    correct = sub.add_parser("correct", help="apply verification corrections to imported recipes")
    correct.add_argument("corrections", help="a corrections JSON file, or a directory of them")
    sub.add_parser("status", help="show import progress")

    args = parser.parse_args()
    return {
        "extract": cmd_extract,
        "push": cmd_push,
        "images": cmd_images,
        "cookbooks": cmd_cookbooks,
        "correct": cmd_correct,
        "status": cmd_status,
    }[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
