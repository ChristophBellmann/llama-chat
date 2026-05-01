#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$ROOT_DIR/env.local.sh"
cd "$ROOT_DIR"

REPLY_MODEL="${REPLY_MODEL:-$ROOT_DIR/models/voice/Qwen2.5-7B-Instruct-Q4_K_M.gguf}"
ORPHEUS_MODEL="${ORPHEUS_MODEL:-$(./voice/run.sh orpheus-path)}"

REPLY_PORT="${REPLY_PORT:-8081}"
ORPHEUS_PORT="${ORPHEUS_PORT:-8082}"

REPLY_CTX="${REPLY_CTX:-8192}"
ORPHEUS_CTX="${ORPHEUS_CTX:-2048}"

REPLY_GPU_LAYERS="${REPLY_GPU_LAYERS:--1}"
ORPHEUS_GPU_LAYERS="${ORPHEUS_GPU_LAYERS:--1}"

cleanup() {
  echo
  echo "Beende Voice-Stack..."
  if [[ -n "${REPLY_PID:-}" ]]; then kill "$REPLY_PID" 2>/dev/null || true; fi
  if [[ -n "${ORPHEUS_PID:-}" ]]; then kill "$ORPHEUS_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM

wait_http() {
  local name="$1"
  local url="$2"

  echo "Warte auf $name: $url"
  for _ in $(seq 1 120); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "$name bereit."
      return 0
    fi
    sleep 1
  done

  echo "Fehler: $name wurde nicht rechtzeitig bereit." >&2
  return 1
}

echo "Starte Reply-LLM auf Port $REPLY_PORT"
PORT="$REPLY_PORT" \
MODEL_ALIAS=voice-local \
CTX="$REPLY_CTX" \
GPU_LAYERS="$REPLY_GPU_LAYERS" \
./start_voice_server.sh "$REPLY_MODEL" &
REPLY_PID=$!

echo "Starte Orpheus-TTS auf Port $ORPHEUS_PORT"
PORT="$ORPHEUS_PORT" \
MODEL_ALIAS=orpheus-tts \
CTX="$ORPHEUS_CTX" \
GPU_LAYERS="$ORPHEUS_GPU_LAYERS" \
./start_voice_server.sh "$ORPHEUS_MODEL" &
ORPHEUS_PID=$!

wait_http "Reply-LLM" "http://127.0.0.1:$REPLY_PORT/v1/models"
wait_http "Orpheus-TTS" "http://127.0.0.1:$ORPHEUS_PORT/v1/models"

echo
echo "Starte Voice-Loop..."
echo "  STT:      ${WHISPER_MODEL:-small}"
echo "  Reply:   http://127.0.0.1:$REPLY_PORT/v1/chat/completions"
echo "  TTS:     http://127.0.0.1:$ORPHEUS_PORT/completion"
echo "  SNAC:    ${SNAC_DEVICE:-cpu}"
echo

LLAMA_API_URL="http://127.0.0.1:$REPLY_PORT/v1/chat/completions" \
LLAMA_MODEL=voice-local \
ORPHEUS_COMPLETION_URL="http://127.0.0.1:$ORPHEUS_PORT/completion" \
SNAC_DEVICE="${SNAC_DEVICE:-cpu}" \
WHISPER_MODEL="${WHISPER_MODEL:-small}" \
WHISPER_COMPUTE_TYPE="${WHISPER_COMPUTE_TYPE:-int8}" \
WHISPER_BEAM_SIZE="${WHISPER_BEAM_SIZE:-5}" \
WHISPER_VAD="${WHISPER_VAD:-1}" \
LLAMA_MAX_TOKENS="${LLAMA_MAX_TOKENS:-80}" \
LLAMA_TEMP="${LLAMA_TEMP:-0.7}" \
./voice/run.sh loop --reply llama --tts orpheus-server
