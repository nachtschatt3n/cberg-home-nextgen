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


def _fetch_all(base: str, token: str, endpoint: str) -> dict:
    """name -> id for an organizer collection (units, foods)."""
    found, page = {}, 1
    while True:
        data = _mealie("GET", f"{base}/api/{endpoint}?page={page}&perPage=100", token)
        for item in data.get("items", []):
            found[item["name"].strip().lower()] = item["id"]
        if page >= data.get("total_pages", 1):
            break
        page += 1
    return found


class OrganizerCache:
    """Resolves ingredient units and foods to existing IDs, creating what is missing.

    Mealie's OpenAPI advertises that `unit`/`food` accept a create-shape carrying
    only a name, but the recipe update handler rejects it with
    `ValueError: Expected 'id' to be provided for unit`. Units and foods must
    therefore exist before a recipe can reference them. Resolving up-front also
    keeps the corpus from sprouting near-duplicate foods, since matching is done
    case-insensitively on the trimmed name.
    """

    def __init__(self, base: str, token: str):
        self.base, self.token = base, token
        self.units = _fetch_all(base, token, "units")
        self.foods = _fetch_all(base, token, "foods")

    def _resolve(self, kind: str, cache: dict, name: str) -> dict:
        key = name.strip().lower()
        if key not in cache:
            created = _mealie(
                "POST", f"{self.base}/api/{kind}", self.token, {"name": name.strip()}
            )
            cache[key] = created["id"]
        return {"id": cache[key], "name": name.strip()}

    def apply(self, recipe: dict) -> dict:
        for ing in recipe.get("recipeIngredient") or []:
            for field, kind, cache in (
                ("unit", "units", self.units),
                ("food", "foods", self.foods),
            ):
                value = ing.get(field)
                if isinstance(value, dict) and value.get("name") and not value.get("id"):
                    ing[field] = self._resolve(kind, cache, value["name"])
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
    sub.add_parser("status", help="show import progress")

    args = parser.parse_args()
    return {"extract": cmd_extract, "push": cmd_push, "status": cmd_status}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
