#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CONFIG="$REPO_ROOT/voice/config.yaml"
RUNTIME_DIR="$REPO_ROOT/voice/runtime"
LOG_FILE="$RUNTIME_DIR/voice.log"

mkdir -p "$RUNTIME_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Fehler: python3 nicht gefunden." >&2
  exit 1
fi

python3 - <<'PY'
import sys
try:
    import yaml  # noqa: F401
except Exception:
    print("Fehler: PyYAML fehlt.", file=sys.stderr)
    print("Installiere mit: pip install pyyaml", file=sys.stderr)
    raise SystemExit(1)
PY

if [[ ! -f "$CONFIG" ]]; then
  echo "Fehler: Config fehlt: $CONFIG" >&2
  exit 1
fi

echo "Voice-Loop gestartet."
echo "[Enter] = neue Aufnahme, /q = beenden"

while true; do
  read -r -p "voice> " CMD
  if [[ "$CMD" == "/q" ]]; then
    echo "Beendet durch User-Command."
    break
  fi

  "$SCRIPT_DIR/record_ptt.sh"
  "$SCRIPT_DIR/stt_whispercpp.sh"

  TRANSCRIPT=""
  if [[ -f "$RUNTIME_DIR/in.txt" ]]; then
    TRANSCRIPT="$(cat "$RUNTIME_DIR/in.txt")"
  fi

  if [[ -z "${TRANSCRIPT// }" ]]; then
    echo "Leere Transkription, naechster Durchlauf."
    continue
  fi

  if [[ "$TRANSCRIPT" == *"/q"* ]]; then
    echo "Abbruchkommando in Transkript erkannt."
    break
  fi

  "$SCRIPT_DIR/llm_llamacpp.sh"

  RESPONSE=""
  if [[ -f "$RUNTIME_DIR/out.txt" ]]; then
    RESPONSE="$(cat "$RUNTIME_DIR/out.txt")"
  fi

  "$SCRIPT_DIR/tts_piper.sh"
  "$SCRIPT_DIR/play.sh"

  TS="$(date '+%Y-%m-%d %H:%M:%S')"
  {
    printf '[%s] USER: %s\n' "$TS" "$TRANSCRIPT"
    printf '[%s] ASSISTANT: %s\n\n' "$TS" "$RESPONSE"
  } >> "$LOG_FILE"
done

echo "Voice-Loop beendet."
