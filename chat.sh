#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LLAMA_DIR="$ROOT_DIR/llama.cpp"
LLAMA_BIN="$LLAMA_DIR/build/bin/llama-cli"

VOICE_BIN_DIR="$ROOT_DIR/voice/bin"
RECORD_PTT_SH="$VOICE_BIN_DIR/record_ptt.sh"
STT_SH="$VOICE_BIN_DIR/stt_whispercpp.sh"

DEFAULT_MODEL_CANDIDATES=(
  "$ROOT_DIR/models/Qwen3.6-27B-Q4_K_M.gguf"
  "$ROOT_DIR/models/Qwen3.6-27B-Instruct-Q4_K_M.gguf"
  "$ROOT_DIR/models/Qwen_Qwen3.6-27B-Q4_K_M.gguf"
  "$ROOT_DIR/models/qwen3.6-27b-q4_k_m.gguf"
  "$ROOT_DIR/models/Qwen3.5-9B-Q4_K_M.gguf"
)

usage() {
  cat <<'USAGE'
Usage:
  ./chat.sh [--mode text|speech] [MODEL_PATH]
  ./chat.sh [--speech] [MODEL_PATH]

Modes:
  text    Default. Reiner Textchat (kein TTS/STT).
  speech  Sprach-Loop mit STT + TTS.

Env (optional):
  CHAT_MODE, LLAMA_CTX_SIZE, LLAMA_GPU_LAYERS, LLAMA_THREADS,
  LLAMA_TEMP, LLAMA_TOP_P, LLAMA_N_PREDICT, SYSTEM_PROMPT, TTS_MODEL
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

CHAT_MODE="${CHAT_MODE:-text}"
MODEL_ARG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      CHAT_MODE="$2"
      shift 2
      ;;
    --speech)
      CHAT_MODE="speech"
      shift
      ;;
    --text)
      CHAT_MODE="text"
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

if [[ "$CHAT_MODE" != "text" && "$CHAT_MODE" != "speech" ]]; then
  echo "Fehler: --mode muss 'text' oder 'speech' sein (aktuell: $CHAT_MODE)" >&2
  exit 2
fi

MODEL_PATH="${MODEL_ARG:-$(resolve_default_model)}"

DEFAULT_GPU_LAYERS=99
DEFAULT_CTX_SIZE=4096

# 27B on 12 GB VRAM typically needs lower defaults than smaller models.
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

TTS_MODEL="${TTS_MODEL:-$ROOT_DIR/voice/models/de_DE-thorsten-high.onnx}"
RUNTIME_DIR="$ROOT_DIR/voice/runtime"
OUT_WAV="$RUNTIME_DIR/out.wav"
IN_TXT="$RUNTIME_DIR/in.txt"
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

PIPER_BIN=""
if [[ -x "$ROOT_DIR/.venv-piper/bin/piper" ]]; then
  PIPER_BIN="$ROOT_DIR/.venv-piper/bin/piper"
elif command -v piper >/dev/null 2>&1; then
  PIPER_BIN="$(command -v piper)"
fi

mkdir -p "$RUNTIME_DIR"

export PATH="/opt/rocm/bin:$PATH"
export LD_LIBRARY_PATH="$LLAMA_DIR/build/bin:/opt/rocm/lib:/opt/rocm/lib64:${LD_LIBRARY_PATH:-}"
export HIP_PLATFORM=amd

if [[ "$CHAT_MODE" == "speech" ]]; then
  if [[ ! -x "$RECORD_PTT_SH" ]]; then
    echo "Fehler: Speech-Modus braucht $RECORD_PTT_SH" >&2
    exit 1
  fi
  if [[ ! -x "$STT_SH" ]]; then
    echo "Fehler: Speech-Modus braucht $STT_SH" >&2
    exit 1
  fi
  if [[ -z "$PIPER_BIN" ]]; then
    echo "Fehler: Speech-Modus braucht piper (z. B. .venv-piper/bin/piper)." >&2
    exit 1
  fi
  if [[ ! -f "$TTS_MODEL" ]]; then
    echo "Fehler: Speech-Modus braucht TTS-Modell: $TTS_MODEL" >&2
    exit 1
  fi
  if ! command -v pw-play >/dev/null 2>&1; then
    echo "Fehler: Speech-Modus braucht pw-play." >&2
    exit 1
  fi
fi

run_llama() {
  local user_input="$1"
  local raw_out="$RUNTIME_DIR/.chat_raw.out"
  local err_out="$RUNTIME_DIR/.chat_raw.err"

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
      --prompt "$user_input" \
      > "$raw_out" 2> "$err_out"; then
    echo "Fehler: llama.cpp Aufruf fehlgeschlagen." >&2
    if [[ -s "$err_out" ]]; then
      sed -n '1,12p' "$err_out" >&2
    fi
    if [[ -s "$raw_out" ]]; then
      sed -n '1,12p' "$raw_out" >&2
    fi
    echo "Tipp: Bei VRAM-Problemen mit weniger GPU-Layern/kleinerem Kontext starten, z. B.:" >&2
    echo "  LLAMA_GPU_LAYERS=32 LLAMA_CTX_SIZE=1536 ./chat.sh" >&2
    return 1
  fi

  local clean
  clean="$(sed -E 's/\x1B\[[0-9;]*[A-Za-z]//g' "$raw_out")"

  REPLY="$(printf '%s\n' "$clean" | awk '
    /^> / {capture=1; next}
    /^\[ Prompt:/ {capture=0}
    capture {print}
  ' | sed '/^[[:space:]]*$/d')"

  if [[ -z "${REPLY// }" ]]; then
    REPLY="$(printf '%s\n' "$clean" | sed '/^[[:space:]]*$/d' | tail -n 1)"
  fi

  return 0
}

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

speak_reply() {
  local text="$1"
  if [[ -z "${text// }" ]]; then
    return 0
  fi
  echo "$text" | "$PIPER_BIN" --model "$TTS_MODEL" --output_file "$OUT_WAV" >/dev/null 2>&1 || return 0
  [[ -s "$OUT_WAV" ]] && pw-play "$OUT_WAV" >/dev/null 2>&1 || true
}

read_text_input() {
  local input
  read -r -p ">>> " input || return 1
  USER_INPUT="$input"
  return 0
}

read_speech_input() {
  rm -f "$IN_TXT"

  if ! "$RECORD_PTT_SH"; then
    echo "Hinweis: Aufnahme fehlgeschlagen, naechster Durchlauf." >&2
    return 1
  fi
  if ! "$STT_SH"; then
    echo "Hinweis: STT fehlgeschlagen, naechster Durchlauf." >&2
    return 1
  fi

  USER_INPUT=""
  if [[ -f "$IN_TXT" ]]; then
    USER_INPUT="$(cat "$IN_TXT")"
  fi

  if [[ -z "${USER_INPUT// }" ]]; then
    echo "Hinweis: Leere Transkription, naechster Durchlauf." >&2
    return 1
  fi

  echo "Du (STT): $USER_INPUT"
  return 0
}

echo "Chat gestartet. /exit zum Beenden."
echo "Modus: $CHAT_MODE"
echo "Modell: $(basename "$MODEL_PATH")"
echo "Konfig: ctx=$LLAMA_CTX_SIZE, gpu_layers=$LLAMA_GPU_LAYERS, threads=$LLAMA_THREADS"
if [[ "$CHAT_MODE" == "speech" ]]; then
  echo "Speech aktiv: STT + TTS"
  echo "Ablauf: Aufnahme starten/stoppen via Enter, Beenden per /exit sprechen oder Ctrl+C"
else
  echo "Textmodus aktiv (Default): kein TTS/STT, Antwort wird live gestreamt"
fi

while true; do
  USER_INPUT=""

  if [[ "$CHAT_MODE" == "speech" ]]; then
    if ! read_speech_input; then
      continue
    fi
  else
    if ! read_text_input; then
      break
    fi
  fi

  if [[ "$USER_INPUT" == "/exit" || "$USER_INPUT" == "/q" ]]; then
    break
  fi
  if [[ -z "${USER_INPUT// }" ]]; then
    continue
  fi

  if [[ "$CHAT_MODE" == "speech" ]]; then
    if ! run_llama "$USER_INPUT"; then
      continue
    fi
    echo
    echo "$REPLY"
    echo
    speak_reply "$REPLY"
  else
    run_llama_stream "$USER_INPUT" || continue
    echo
  fi
done

echo "Beendet."
