#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$ROOT_DIR/ollama.pid"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  kill "$(cat "$PID_FILE")"
  rm -f "$PID_FILE"
  echo "Ollama gestoppt."
  exit 0
fi

pkill -f 'ollama serve' || true
rm -f "$PID_FILE"
echo "Kein aktiver Ollama-Prozess gefunden."
