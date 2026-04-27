#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VOICE_DIR="$ROOT_DIR/voice"
PY="$VOICE_DIR/.venv/bin/python3"

source "$VOICE_DIR/env_runtime.sh"

cd "$ROOT_DIR"
exec "$PY" "$@"
