#!/usr/bin/env bash
set -euo pipefail
# Wyoming-TTS-Server fuer Orpheus-DE. Home Assistant auf thinkthing bindet ihn
# als TTS-Entitaet ein. Setzt den Orpheus-llama-server voraus:
#   ./start_orpheus_de_server.sh    (Port 8082, GPU)

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$ROOT_DIR/env.local.sh"
VENV="${VENV_DIR:-$ROOT_DIR/voice/.venv}"

export PYTHONPATH="$ROOT_DIR/voice:$ROOT_DIR:${PYTHONPATH:-}"
export SNAC_DEVICE="${SNAC_DEVICE:-cpu}"
export ORPHEUS_COMPLETION_URL="${ORPHEUS_COMPLETION_URL:-http://127.0.0.1:8082/completion}"
export ORPHEUS_VOICE="${ORPHEUS_VOICE:-jana}"

PORT="${WYOMING_PORT:-10401}"
echo "Starte Wyoming-Orpheus auf tcp://0.0.0.0:$PORT"
exec "$VENV/bin/python3" "$ROOT_DIR/profiles/wyoming-orpheus/server.py" \
  --uri "tcp://0.0.0.0:$PORT" "$@"
