#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$ROOT_DIR/env.local.sh"
MODEL_PATH="${1:-$ROOT_DIR/models/Qwen3.6-35B-A3B-UD-IQ2_M.gguf}"
MODEL_ID="${MODEL_ID:-llama.cpp/locales_llm}"
MODEL_ALIAS="${MODEL_ALIAS:-${MODEL_ID#*/}}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8080}"
API_KEY="${API_KEY:-sk-local}"

cd "$ROOT_DIR"

MODEL_ALIAS="$MODEL_ALIAS" ./start_llama_server.sh "$MODEL_PATH" > /tmp/llama_server_opencode.log 2>&1 &
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

if ! grep -Fq "\"$MODEL_ALIAS\"" /tmp/llama_models_opencode.json; then
  echo "Fehler: $MODEL_ALIAS wurde nicht unter /v1/models gefunden" >&2
  echo "Siehe Log: /tmp/llama_server_opencode.log" >&2
  exit 1
fi

# /v1/models can succeed before the model is fully ready for chat completions.
# Wait until a minimal non-stream chat request returns 200.
READY_PAYLOAD="{\"model\":\"$MODEL_ALIAS\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}],\"max_tokens\":1}"
READY=0
for i in $(seq 1 120); do
  HTTP_CODE="$(curl -sS -o /tmp/llama_ready_opencode.json -w "%{http_code}" \
    "http://$HOST:$PORT/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $API_KEY" \
    -d "$READY_PAYLOAD" || true)"
  if [[ "$HTTP_CODE" == "200" ]]; then
    READY=1
    break
  fi
  sleep 1
done

if [[ "$READY" != "1" ]]; then
  echo "Fehler: llama-server ist erreichbar, aber chat/completions wurde nicht rechtzeitig bereit" >&2
  echo "Letzte Antwort: /tmp/llama_ready_opencode.json" >&2
  echo "Siehe Log: /tmp/llama_server_opencode.log" >&2
  exit 1
fi

echo "llama-server bereit auf http://$HOST:$PORT/v1 (Model alias: $MODEL_ALIAS)"
echo "Starte OpenCode mit Modell $MODEL_ID"

exec opencode -m "$MODEL_ID"
