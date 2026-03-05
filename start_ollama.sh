#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OLLAMA_HOME_DIR="$ROOT_DIR/ollama-local"
OLLAMA_BIN="$OLLAMA_HOME_DIR/bin/ollama"
LOG_FILE="$ROOT_DIR/ollama.log"
PID_FILE="$ROOT_DIR/ollama.pid"

if [[ ! -x "$OLLAMA_BIN" ]]; then
  echo "Fehler: $OLLAMA_BIN nicht gefunden."
  exit 1
fi

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Ollama läuft bereits (PID $(cat "$PID_FILE"))."
  exit 0
fi

export PATH="$OLLAMA_HOME_DIR/bin:$PATH"
export OLLAMA_HOST="127.0.0.1:11434"
export OLLAMA_MODELS="$ROOT_DIR/ollama-models"
export LD_LIBRARY_PATH="/opt/rocm/lib:/opt/rocm/lib64:${LD_LIBRARY_PATH:-}"
export HIP_VISIBLE_DEVICES="0"
export HSA_OVERRIDE_GFX_VERSION="10.3.0"

mkdir -p "$OLLAMA_MODELS"

nohup "$OLLAMA_BIN" serve >"$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

for _ in {1..60}; do
  if curl -fsS "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
    echo "Ollama läuft auf $OLLAMA_HOST"
    exit 0
  fi
  sleep 1
done

echo "Ollama wurde gestartet, API antwortet aber noch nicht. Siehe $LOG_FILE"
exit 1
