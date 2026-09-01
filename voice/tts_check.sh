#!/usr/bin/env bash
set -euo pipefail
# TTS-Backends vergleichen: Latenz (cold/warm), WAV-Ausgabe, Rueck-Transkription.
#
#   ./voice/tts_check.sh                                  # alle Backends, 3 Laeufe
#   ./voice/tts_check.sh --tts neutts --runs 5 "Mein Text"
#   ./voice/tts_check.sh --tts orpheus-server --no-transcribe
#
# Orpheus braucht einen laufenden Server:
#   ./start_orpheus_de_server.sh    (Port 8082)

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/env.local.sh"
VOICE_DIR="$ROOT_DIR/voice"
VENV_DIR="${VENV_DIR:-$VOICE_DIR/.venv}"

export PYTHONPATH="$VOICE_DIR:$ROOT_DIR:${PYTHONPATH:-}"
export SNAC_DEVICE="${SNAC_DEVICE:-cpu}"
export ORPHEUS_COMPLETION_URL="${ORPHEUS_COMPLETION_URL:-http://127.0.0.1:8082/completion}"
export NEUTTS_REF_AUDIO="${NEUTTS_REF_AUDIO:-$ROOT_DIR/voices}"
export PIPER_BIN="${PIPER_BIN:-$ROOT_DIR/.venv-piper/bin/piper}"
export PIPER_MODEL="${PIPER_MODEL:-$VOICE_DIR/models/piper/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx}"

exec "$VENV_DIR/bin/python3" "$VOICE_DIR/tts_check.py" "$@"
