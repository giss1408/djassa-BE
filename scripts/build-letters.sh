#!/usr/bin/env bash
# Render the letters of interest (scripts/letters/*.html) to A4 PDFs in
# backend-api/app/investor_brief/, served behind the investor password with
# the brief that links them (app/api/investor_brief.py). Run after editing a
# letter; the PDFs are committed, so deploying does not need Chrome.
#
# Text source: docs/business/LETTERS-OF-INTEREST(.fr).md. Keep the two in
# step: a change to the wording is a change to both.
#
# Usage: scripts/build-letters.sh   (needs Google Chrome or Chromium)
set -euo pipefail

cd "$(dirname "$0")/.."

CHROME="${CHROME:-}"
if [ -z "$CHROME" ]; then
  for candidate in \
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    "$(command -v google-chrome || true)" \
    "$(command -v chromium || true)"; do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then CHROME="$candidate"; break; fi
  done
fi
if [ -z "$CHROME" ]; then
  echo "error: Chrome not found; set CHROME=/path/to/chrome" >&2
  exit 1
fi

for source in scripts/letters/*.html; do
  name="$(basename "$source" .html)"
  "$CHROME" --headless=new --disable-gpu --no-pdf-header-footer \
    --print-to-pdf="backend-api/app/investor_brief/$name.pdf" "file://$PWD/$source" 2>/dev/null
  echo "backend-api/app/investor_brief/$name.pdf"
done
