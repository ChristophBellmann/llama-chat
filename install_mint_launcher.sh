#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_TEMPLATE="$REPO_DIR/systemd/llama-server.service.in"
SERVICE_TARGET="$HOME/.config/systemd/user/llama-server.service"
APP_DIR="$HOME/.local/share/applications"

mkdir -p "$HOME/.config/systemd/user" "$APP_DIR"

awk -v repo="$REPO_DIR" '{ gsub(/__REPO_DIR__/, repo); print }' "$SERVICE_TEMPLATE" > "$SERVICE_TARGET"
install -m 644 "$REPO_DIR/desktop/llama-server-start.desktop" "$APP_DIR/llama-server-start.desktop"
install -m 644 "$REPO_DIR/desktop/llama-server-stop.desktop" "$APP_DIR/llama-server-stop.desktop"

systemctl --user daemon-reload
systemctl --user enable llama-server.service
update-desktop-database "$APP_DIR" || true

echo "Installed LLAMA Mint launcher entries and user service."
echo "Use: systemctl --user start|stop|status llama-server.service"
