#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$ROOT_DIR/llama.cpp/build/bin"
MODEL_PATH="${1:-$ROOT_DIR/models/Qwen3.6-35B-A3B-UD-IQ2_M.gguf}"
MODEL_ALIAS="${MODEL_ALIAS:-qwen-local}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8080}"
CTX="${CTX:-32768}"
GPU_LAYERS="${GPU_LAYERS:--1}"
CACHE_TYPE_K="${CACHE_TYPE_K:-q8_0}"
CACHE_TYPE_V="${CACHE_TYPE_V:-q8_0}"
LONG_CONTEXT="${LONG_CONTEXT:-0}"
ROPE_SCALING="${ROPE_SCALING:-yarn}"
ROPE_SCALE="${ROPE_SCALE:-2.0}"
YARN_ORIG_CTX="${YARN_ORIG_CTX:-0}"
YARN_EXT_FACTOR="${YARN_EXT_FACTOR:--1.0}"
YARN_ATTN_FACTOR="${YARN_ATTN_FACTOR:--1.0}"
YARN_BETA_SLOW="${YARN_BETA_SLOW:--1.0}"
YARN_BETA_FAST="${YARN_BETA_FAST:--1.0}"

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

echo "Starte llama-server"
echo "  model: $MODEL_PATH"
echo "  alias: $MODEL_ALIAS"
echo "  url:   http://$HOST:$PORT/v1"
echo "  ctx:   $CTX"
echo "  ngl:   $GPU_LAYERS"
echo "  ctk:   $CACHE_TYPE_K"
echo "  ctv:   $CACHE_TYPE_V"
echo "  long:  $LONG_CONTEXT"
if [[ "$LONG_CONTEXT" == "1" ]]; then
  echo "  rope:  $ROPE_SCALING (scale=$ROPE_SCALE)"
fi
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

if [[ "$LONG_CONTEXT" == "1" ]]; then
  ARGS+=(
    --rope-scaling "$ROPE_SCALING"
    --rope-scale "$ROPE_SCALE"
    --yarn-orig-ctx "$YARN_ORIG_CTX"
    --yarn-ext-factor "$YARN_EXT_FACTOR"
    --yarn-attn-factor "$YARN_ATTN_FACTOR"
    --yarn-beta-slow "$YARN_BETA_SLOW"
    --yarn-beta-fast "$YARN_BETA_FAST"
  )
fi

exec "$BIN_DIR/llama-server" "${ARGS[@]}"
