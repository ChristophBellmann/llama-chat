#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$ROOT_DIR/env.local.sh"

VENV="$ROOT_DIR/.venv-llm/bin/activate"
SCRIPT="$ROOT_DIR/llama.cpp/convert_hf_to_gguf_update.py"

if [[ ! -f "$VENV" ]]; then
  echo "Fehler: venv nicht gefunden: $VENV" >&2
  exit 1
fi

if [[ ! -f "$SCRIPT" ]]; then
  echo "Fehler: Script nicht gefunden: $SCRIPT" >&2
  exit 1
fi

source "$VENV"
cd "$ROOT_DIR/llama.cpp"

echo "HF_HOME: $HF_HOME"
echo "Token erwartet unter: $HF_HOME/token"

TOKEN_FILE="$HF_HOME/token"

if [[ "$#" -eq 0 ]] || [[ "${1:-}" == --* ]]; then
  if [[ -s "$TOKEN_FILE" ]]; then
    exec python convert_hf_to_gguf_update.py "$(cat "$TOKEN_FILE")" "$@"
  fi
fi

exec python convert_hf_to_gguf_update.py "$@"
