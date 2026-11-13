#!/bin/sh
# Copy the packaged plugin to a Steam Deck over SSH and restart Decky.
#
#   scripts/deploy.sh [user@host]      (default deck@steamdeck.local)
#
# Needs SSH enabled on the Deck (Desktop Mode: `passwd`, then
# `sudo systemctl enable --now sshd`). Asks for the Deck's sudo password,
# because Decky's plugins folder belongs to root.
set -eu

root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
target=${1:-deck@steamdeck.local}

"$root/scripts/package.sh"
scp "$root/out/HexDeck.zip" "$target:/tmp/HexDeck.zip"
ssh -t "$target" '
  set -e
  plugins="$HOME/homebrew/plugins"
  cd /tmp && rm -rf /tmp/HexDeck && unzip -q /tmp/HexDeck.zip
  sudo rm -rf "$plugins/HexDeck"
  sudo mv /tmp/HexDeck "$plugins/HexDeck"
  sudo systemctl restart plugin_loader
  rm -f /tmp/HexDeck.zip
  echo "Installed HexDeck; Decky restarted."
'
