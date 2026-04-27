#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$ROOT_DIR/llama.cpp/build/bin"

MODEL_PATH="${1:-$ROOT_DIR/models/voice/Qwen2.5-7B-Instruct-Q4_K_M.gguf}"
MODEL_ALIAS="${MODEL_ALIAS:-voice-local}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8081}"
CTX="${CTX:-8192}"
GPU_LAYERS="${GPU_LAYERS:--1}"
CACHE_TYPE_K="${CACHE_TYPE_K:-q8_0}"
CACHE_TYPE_V="${CACHE_TYPE_V:-q8_0}"

if [[ ! -x "$BIN_DIR/llama-server" ]]; then
  echo "Fehler: llama-server nicht gefunden unter $BIN_DIR/llama-server" >&2
  exit 1
fi

if [[ ! -f "$MODEL_PATH" ]]; then
  echo "Fehler: Modell nicht gefunden: $MODEL_PATH" >&2
  echo "Nutze: $0 /absoluter/pfad/zum/model.gguf" >&2
  exit 1
fi

export LD_LIBRARY_PATH="$BIN_DIR:${LD_LIBRARY_PATH:-}"

echo "Starte voice llama-server"
echo "  model: $MODEL_PATH"
echo "  alias: $MODEL_ALIAS"
echo "  url:   http://$HOST:$PORT/v1"
echo "  ctx:   $CTX"
echo "  ngl:   $GPU_LAYERS"
echo "  ctk:   $CACHE_TYPE_K"
echo "  ctv:   $CACHE_TYPE_V"

ARGS=(
  -m "$MODEL_PATH"
  --alias "$MODEL_ALIAS"
  --host "$HOST"
  --port "$PORT"
  -ngl "$GPU_LAYERS"
  -c "$CTX"
  -ctk "$CACHE_TYPE_K"
  -ctv "$CACHE_TYPE_V"
  --jinja
)

exec "$BIN_DIR/llama-server" "${ARGS[@]}"
