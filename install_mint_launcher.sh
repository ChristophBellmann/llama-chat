#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
APP_DIR="$HOME/.local/share/applications"

mkdir -p "$UNIT_DIR" "$APP_DIR"

for unit in llama-server.service orpheus-llm.service wyoming-orpheus.service orpheus-manual.target; do
  awk -v repo="$REPO_DIR" '{ gsub(/__REPO_DIR__/, repo); print }' \
    "$REPO_DIR/systemd/$unit.in" > "$UNIT_DIR/$unit"
done
for entry in llama-server-start llama-server-stop orpheus-start orpheus-stop; do
  install -m 644 "$REPO_DIR/desktop/$entry.desktop" "$APP_DIR/$entry.desktop"
done

systemctl --user daemon-reload
systemctl --user enable llama-server.service
update-desktop-database "$APP_DIR" || true

echo "Installed LLAMA and Orpheus Mint launcher entries and user services."
echo "Orpheus Start/Stop controls both the TTS model and its Wyoming bridge."
