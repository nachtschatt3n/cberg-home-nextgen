# Runbook: Import Paperless recipe scans into Mealie

**Version:** 2026.08.24
**Script:** `runbooks/mealie-import.py`

## What this does

Turns the household's scanned recipe cards — archived in Paperless-ngx as
`document_type=12` ("Food") — into structured Mealie recipes with per-ingredient
quantity/unit/food, steps, tags and nutrition.

Paperless is **read-only** throughout. It stays the archival source of truth; every
Mealie recipe carries `extras.paperless_key` (`<doc_id>-p<page>`) pointing back at
the scan it came from.

## Corpus shape (verified 2026-08-24)

| Fact | Value |
|---|---|
| Documents | **154** (`document_type=12`, equivalently tag 38 `Food`) |
| Recipes | **159** — a document can hold several cards |
| Filter to use | `document_type=12`. **Not** the `Recipe` tag 51: it returns 147 and silently drops 7 genuine cards |
| Page pattern | Each card is 2 PDF pages, one photo + one content. 4- and 6-page scans are 2 and 3 recipes, *not* one recipe spanning pages |
| Titles | 147 documents carry a real dish name; 12 recipes need the title read off the card |
| Layout families | `A-multiserving` 118 · `C-bulletlist` 27 · `B-2person` 14 |

## Why it does not use Mealie's built-in AI importer

Mealie ships `POST /api/recipes/create/ai`. Benchmarked against local Ollama
(`gemma4:26b`) on 2026-08-24 it took **9m53s for one card** — roughly 25 hours for
the corpus, saturating a host that paperless-gpt, LibreChat and Sure also use —
and produced unusable output: all 16 ingredients in one unstructured `note`,
`recipeServings` 0, no tags.

The bottleneck was the **input**, not the model. Paperless' `content` field is
flattened OCR, which destroys the card's geometry:

```
Hahnchen 1100g 1500g 1.500g        <- the 2P / 3P / 4P columns, collapsed
```

`pdftotext -layout` keeps those columns in distinct character ranges, so this
script re-extracts from the archived PDF instead. Extraction is deterministic and
takes **~10 seconds for all 159**.

## Layout families and how servings are chosen

The stored base is **4 servings**.

| Family | Card shape | Rule |
|---|---|---|
| `A-multiserving` | HelloFresh table, one quantity column per serving size (`2P 3P 4P`) | take the 4P column |
| `B-2person` | 2-person card stating *"für 4 Personen alle Zutaten verdoppeln"* | double, record `extras.scaled_from` |
| `C-bulletlist` | Marley Spoon bullets under *"Was du von uns bekommst"* | keep the card's own serving count — the card gives no scaling rule, so inventing one would be a guess |

## Running it

Both services are reached over port-forwards; Paperless has no external ingress and
the Mealie ingress caps a request at 900s.

```bash
kubectl -n office port-forward svc/paperless-ngx 8010:8000 &
kubectl -n office port-forward svc/mealie 9010:9000 &

export PAPERLESS_TOKEN=...   # from kubernetes/apps/ai/openclaw/app/secret.sops.yaml
export MEALIE_TOKEN=...      # Mealie → user profile → API tokens

python3 runbooks/mealie-import.py extract
# -> ~/.cache/mealie-import/extractions.json  (one entry per recipe)

# the semantic parse happens here: agents read extractions.json and emit Mealie
# payloads; see "Agent parse" below

python3 runbooks/mealie-import.py push ~/.cache/mealie-import/parsed.json
python3 runbooks/mealie-import.py status
```

`push` is **resumable**. It reads back every recipe's `extras.paperless_key` and
skips what already landed, so a re-run after a partial failure does not create a
second copy of the corpus.

## Agent parse

`extract` produces layout-preserved text per recipe; agents convert it to Mealie
payloads in batches. The brief each agent works from must state:

- **the output contract** — a JSON array, one object per input recipe, same order,
  `extras.paperless_key` copied verbatim from the input `key` (this is the resume
  key: a wrong value silently duplicates the recipe on the next run)
- **the serving rule for each layout family** (table above)
- **the OCR repair table** (below) — the damage is mechanical, so it is fixable
  rather than something to copy through
- **step-column reading order** — `A-multiserving` cards lay steps out in three
  columns across two bands; they must be read in printed numbered order, not line
  order, or the method comes out scrambled
- that `unit`/`food` are `{"name": ...}` objects, `quantity` is a number (never a
  range or a string), and nutrition values are bare numeric strings from the
  **per-portion** column, not per-100g
- that bracketed alternates in step text (`1 EL [1,5 EL | 2 EL]`) are the
  2P/3P/4P variants — keep only the value matching the stored serving size

Ask for a per-recipe `extras.parse_confidence` and have low/medium ones reported
back; those are the ones worth reviewing by hand.

Systematic OCR damage the parse must repair (the scanner is consistent about it):

| Seen | Means |
|---|---|
| `208`, `4008`, `1505`, `2009` | trailing `g` misread as `8`/`5`/`9` |
| `OSEL`, `O75 EL`, `TEL` | `0,5 EL`, `0,75 EL`, `1 EL` |
| `Karto eln`, `Pfe er`, `Sonnen ocken` | `ff`/`fl` ligature dropped by OCR |
| `Hahnchen`, `Hirtenkase`, `Ol` | umlaut lost |

## Verification

```bash
python3 runbooks/mealie-import.py status     # recipes == traceable == 159
```

Then in Mealie confirm on a sample: ingredients have `quantity` + `food` populated
(not one prose blob), `recipeServings` is non-zero, tags carried over, and the
4- and 6-page scans produced 2 and 3 *separate* recipes.

## Gotchas

- **`unit`/`food` need IDs.** The OpenAPI advertises a create-shape carrying only
  a name, but the recipe update handler rejects it with
  `ValueError: Expected 'id' to be provided for unit`. `OrganizerCache` pre-creates
  and resolves them; do not hand-write payloads with bare names.
- **Recipe creation is two calls.** `POST /api/recipes` accepts only a name; the
  body goes in a follow-up `PUT` against the returned slug. If that PUT fails the
  script deletes the shell — a leftover shell occupies the slug *and* counts as an
  imported recipe while holding none of its content.
- **Recipe content must never enter git.** The repository is public and these are
  Paperless document bodies (`docs/sops/paperless.md` §10). `extract` refuses to
  write anywhere inside the repo; do not work around the guard.
- **Content-page detection is invariant-checked.** A document must yield exactly
  `pages / 2` content pages; the script raises if not, because the alternative is a
  silently incomplete import.
