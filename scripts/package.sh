#!/bin/sh
# Build the frontend and write out/HexDeck.zip, the archive Decky's
# "Install Plugin from ZIP" accepts: one HexDeck/ folder with plugin.json,
# main.py, the built frontend and the Python package.
set -eu

root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

if [ "${SKIP_BUILD:-}" != 1 ]; then
  npm run build
fi
test -f dist/index.js || { echo "dist/index.js is missing; run npm run build" >&2; exit 1; }

stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
plugin="$stage/HexDeck"
mkdir -p "$plugin/assets" "$plugin/dist" "$plugin/py_modules/hexdeck"
cp plugin.json package.json main.py README.md LICENSE THIRD_PARTY_NOTICES.md "$plugin/"
cp assets/hexdeck-banner.webp "$plugin/assets/"
cp dist/index.js "$plugin/dist/"
cp py_modules/hexdeck/*.py "$plugin/py_modules/hexdeck/"

mkdir -p out
rm -f out/HexDeck.zip
(cd "$stage" && zip -qr "$root/out/HexDeck.zip" HexDeck -x '*/__pycache__/*')
echo "Wrote out/HexDeck.zip"
unzip -l out/HexDeck.zip
