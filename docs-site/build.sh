#!/bin/sh
# Assemble the mkdocs staging tree and build the static site.
# POSIX/busybox-safe: runs inside the squidfunk/mkdocs-material image (Alpine).
#
# Usage: build.sh <repo-dir> <output-dir>
#   repo-dir   fresh clone of this repository
#   output-dir directory the rendered site is written to (nginx docroot)
#
# The staging tree (docs-site/content) mirrors the repo root: docs/ is copied
# wholesale (including diagrams/ HTML served verbatim) and runbooks contributes
# only its *.md files, subdirectories preserved. That keeps every repo-relative
# cross-link working without rewriting.
set -eu

REPO_DIR="${1:?usage: build.sh <repo-dir> <output-dir>}"
OUT_DIR="${2:?usage: build.sh <repo-dir> <output-dir>}"
SRC="$REPO_DIR/docs-site/content"

rm -rf "$SRC"
mkdir -p "$SRC"

cp -r "$REPO_DIR/docs" "$SRC/docs"

# Runbook markdown only (scripts/YAML must not become pages), keeping subdirs
# like runbooks/maintenance/plans/. busybox tar supports -T -.
(cd "$REPO_DIR" && find runbooks -name '*.md' -type f | tar cf - -T -) | tar xf - -C "$SRC"

cp "$REPO_DIR/docs-site/index.md" "$SRC/index.md"

mkdocs build -f "$REPO_DIR/docs-site/mkdocs.yml" -d "$OUT_DIR"
