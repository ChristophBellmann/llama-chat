#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VOICE_DIR="$ROOT_DIR/voice"
MODEL_DIR="$VOICE_DIR/models"
HUGGINGFACE_REPO="coqui/Orpheus"
MODEL_FILE="Orpheus-Q4_K_M.gguf"
MODEL_PATH="$MODEL_DIR/$MODEL_FILE"

if [[ -f "$MODEL_PATH" ]]; then
  echo "Modell bereits vorhanden: $MODEL_PATH"
  exit 0
fi

mkdir -p "$MODEL_DIR"

echo "Lade Orpheus Q4_K_M von HuggingFace..."
huggingface-cli download "$HUGGINGFACE_REPO" "$MODEL_FILE" --local-dir "$MODEL_DIR" || {
  echo "Fehler: huggingface-cli nicht verfuegbar" >&2
  echo "Installiere mit: pip install huggingface-hub" >&2
  exit 1
}

echo "Done: $MODEL_PATH"