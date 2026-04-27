#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VOICE_DIR="$ROOT_DIR/voice"
PY="$VOICE_DIR/.venv/bin/python3"

if [[ ! -x "$PY" ]]; then
  echo "Fehler: Python venv fehlt. Erst ausführen: ./voice/setup_voice_env.sh" >&2
  exit 1
fi

source "$VOICE_DIR/env_runtime.sh"

cd "$ROOT_DIR"
export ORPHEUS_GPU_LAYERS="${ORPHEUS_GPU_LAYERS:-0}"
export SNAC_DEVICE="${SNAC_DEVICE:-cpu}"
exec "$PY" "$VOICE_DIR/run_tts_llamacpp.py" "$@"
