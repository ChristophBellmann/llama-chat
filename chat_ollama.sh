#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OLLAMA_HOME_DIR="$ROOT_DIR/ollama-local"
OLLAMA_BIN="$OLLAMA_HOME_DIR/bin/ollama"
MODEL="${1:-qwen35-local}"

if [[ ! -x "$OLLAMA_BIN" ]]; then
  echo "Fehler: $OLLAMA_BIN nicht gefunden."
  exit 1
fi

"$ROOT_DIR/start_ollama.sh"

export PATH="$OLLAMA_HOME_DIR/bin:$PATH"
export OLLAMA_HOST="127.0.0.1:11434"
export OLLAMA_MODELS="$ROOT_DIR/ollama-models"
export LD_LIBRARY_PATH="/opt/rocm/lib:/opt/rocm/lib64:${LD_LIBRARY_PATH:-}"
export HIP_VISIBLE_DEVICES="0"
export HSA_OVERRIDE_GFX_VERSION="10.3.0"

# Auto-create local model from GGUF if needed.
if [[ "$MODEL" == "qwen35-local" ]]; then
  if ! "$OLLAMA_BIN" list | awk 'NR>1 {print $1}' | grep -Fxq "qwen35-local:latest"; then
    if [[ ! -f "$ROOT_DIR/Modelfile.qwen35-local" ]]; then
      echo "Fehler: $ROOT_DIR/Modelfile.qwen35-local fehlt."
      exit 1
    fi
    "$OLLAMA_BIN" create qwen35-local -f "$ROOT_DIR/Modelfile.qwen35-local"
  fi
fi

exec "$OLLAMA_BIN" run "$MODEL"
