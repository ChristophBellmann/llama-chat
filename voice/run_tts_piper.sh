#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VOICE_DIR="$ROOT_DIR/voice"
PY="$VOICE_DIR/.venv/bin/python3"

if [[ ! -x "$PY" ]]; then
  echo "Fehler: Python venv fehlt. Erst ausführen: ./voice/setup_piper_env.sh" >&2
  exit 1
fi

cd "$ROOT_DIR"
exec "$PY" "$VOICE_DIR/run_tts_piper.py" "$@"
