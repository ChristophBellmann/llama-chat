#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_PATH="${1:-$ROOT_DIR/models/Qwen3.6-35B-A3B-UD-IQ2_M.gguf}"
MODEL_ID="${MODEL_ID:-llama.cpp/qwen-local}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8080}"
API_KEY="${API_KEY:-sk-local}"

cd "$ROOT_DIR"

./start_llama_server.sh "$MODEL_PATH" > /tmp/llama_server_opencode.log 2>&1 &
LLAMA_PID=$!

cleanup() {
  kill "$LLAMA_PID" 2>/dev/null || true
  wait "$LLAMA_PID" 2>/dev/null || true
}
trap cleanup EXIT

for i in $(seq 1 120); do
  if curl -fsS "http://$HOST:$PORT/v1/models" -H "Authorization: Bearer $API_KEY" >/tmp/llama_models_opencode.json 2>/dev/null; then
    break
  fi
  sleep 1
done

if ! rg -q 'qwen-local' /tmp/llama_models_opencode.json; then
  echo "Fehler: qwen-local wurde nicht unter /v1/models gefunden" >&2
  echo "Siehe Log: /tmp/llama_server_opencode.log" >&2
  exit 1
fi

echo "llama-server bereit auf http://$HOST:$PORT/v1 (Model alias: qwen-local)"
echo "Starte OpenCode mit Modell $MODEL_ID"

exec opencode -m "$MODEL_ID"
