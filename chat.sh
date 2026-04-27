#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LLAMA_DIR="$ROOT_DIR/llama.cpp"
LLAMA_BIN="$LLAMA_DIR/build/bin/llama-cli"

DEFAULT_MODEL_CANDIDATES=(
  "$ROOT_DIR/models/Qwen3-14B-Q4_K_M.gguf"
  "$ROOT_DIR/models/Qwen3.6-27B-Q4_K_M.gguf"
  "$ROOT_DIR/models/Qwen3.6-27B-Instruct-Q4_K_M.gguf"
  "$ROOT_DIR/models/Qwen_Qwen3.6-27B-Q4_K_M.gguf"
  "$ROOT_DIR/models/qwen3.6-27b-q4_k_m.gguf"
  "$ROOT_DIR/models/Qwen3.5-9B-Q4_K_M.gguf"
)

usage() {
  cat <<'USAGE'
Usage:
  ./chat.sh [MODEL_PATH]

Env (optional):
  LLAMA_CTX_SIZE, LLAMA_GPU_LAYERS, LLAMA_THREADS,
  LLAMA_TEMP, LLAMA_TOP_P, LLAMA_N_PREDICT, SYSTEM_PROMPT
USAGE
}

resolve_default_model() {
  local candidate
  for candidate in "${DEFAULT_MODEL_CANDIDATES[@]}"; do
    if [[ -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  printf '%s\n' "${DEFAULT_MODEL_CANDIDATES[0]}"
}

MODEL_ARG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --text)
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --*)
      echo "Fehler: Unbekannte Option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [[ -n "$MODEL_ARG" ]]; then
        echo "Fehler: Mehr als ein MODEL_PATH angegeben." >&2
        usage >&2
        exit 2
      fi
      MODEL_ARG="$1"
      shift
      ;;
  esac
done

MODEL_PATH="${MODEL_ARG:-$(resolve_default_model)}"

DEFAULT_GPU_LAYERS=99
DEFAULT_CTX_SIZE=4096

if [[ "${LLAMA_GPU_LAYERS+x}" != "x" ]] && [[ "$MODEL_PATH" =~ 27[Bb] ]]; then
  DEFAULT_GPU_LAYERS=40
fi
if [[ "${LLAMA_CTX_SIZE+x}" != "x" ]] && [[ "$MODEL_PATH" =~ 27[Bb] ]]; then
  DEFAULT_CTX_SIZE=2048
fi

LLAMA_GPU_LAYERS="${LLAMA_GPU_LAYERS:-$DEFAULT_GPU_LAYERS}"
LLAMA_CTX_SIZE="${LLAMA_CTX_SIZE:-$DEFAULT_CTX_SIZE}"
LLAMA_THREADS="${LLAMA_THREADS:-$(nproc)}"
LLAMA_TEMP="${LLAMA_TEMP:-0.7}"
LLAMA_TOP_P="${LLAMA_TOP_P:-0.9}"
LLAMA_N_PREDICT="${LLAMA_N_PREDICT:-320}"
SYSTEM_PROMPT="${SYSTEM_PROMPT:-Du bist ein hilfreicher Assistent. Antworte auf Deutsch, klar und kurz.}"

if [[ ! -x "$LLAMA_BIN" ]]; then
  echo "Fehler: llama-cli nicht gefunden unter $LLAMA_BIN" >&2
  exit 1
fi

if [[ ! -f "$MODEL_PATH" ]]; then
  echo "Fehler: Modell nicht gefunden: $MODEL_PATH" >&2
  echo "Lege z. B. ein Qwen3.6-27B-GGUF unter models/ ab oder gib einen Pfad an:" >&2
  echo "  ./chat.sh /pfad/zu/Qwen3.6-27B-*.gguf" >&2
  exit 1
fi

export PATH="/opt/rocm/bin:$PATH"
export LD_LIBRARY_PATH="$LLAMA_DIR/build/bin:/opt/rocm/lib:/opt/rocm/lib64:${LD_LIBRARY_PATH:-}"
export HIP_PLATFORM=amd

run_llama_stream() {
  local user_input="$1"
  if ! "$LLAMA_BIN" \
      --log-disable \
      --simple-io \
      --no-display-prompt \
      --color off \
      --conversation \
      --single-turn \
      --model "$MODEL_PATH" \
      --gpu-layers "$LLAMA_GPU_LAYERS" \
      --fit on \
      --ctx-size "$LLAMA_CTX_SIZE" \
      --threads "$LLAMA_THREADS" \
      --prio 2 \
      --temp "$LLAMA_TEMP" \
      --top-p "$LLAMA_TOP_P" \
      --n-predict "$LLAMA_N_PREDICT" \
      --system-prompt "$SYSTEM_PROMPT" \
      --prompt "$user_input"; then
    echo "Fehler: llama.cpp Aufruf fehlgeschlagen." >&2
    echo "Tipp: Bei VRAM-Problemen mit weniger GPU-Layern/kleinerem Kontext starten, z. B.:" >&2
    echo "  LLAMA_GPU_LAYERS=32 LLAMA_CTX_SIZE=1536 ./chat.sh" >&2
    return 1
  fi
  return 0
}

read_text_input() {
  local input
  read -r -p ">>> " input || return 1
  USER_INPUT="$input"
  return 0
}

echo "Chat gestartet. /exit zum Beenden."
echo "Modell: $(basename "$MODEL_PATH")"
echo "Konfig: ctx=$LLAMA_CTX_SIZE, gpu_layers=$LLAMA_GPU_LAYERS, threads=$LLAMA_THREADS"
echo "Textmodus (Default): Antwort wird live gestreamt"

while true; do
  USER_INPUT=""

  if ! read_text_input; then
    break
  fi

  if [[ "$USER_INPUT" == "/exit" || "$USER_INPUT" == "/q" ]]; then
    break
  fi
  if [[ -z "${USER_INPUT// }" ]]; then
    continue
  fi

  run_llama_stream "$USER_INPUT" || continue
  echo
done

echo "Beendet."