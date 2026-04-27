#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VOICE_DIR="$ROOT_DIR/voice"
VENV_DIR="${VENV_DIR:-$VOICE_DIR/.venv}"
PY="$VENV_DIR/bin/python3"

cmd="${1:-}"
if [[ -z "$cmd" ]]; then
  cat <<'USAGE'
Usage:
  ./voice/run.sh setup
  ./voice/run.sh download-piper [voice]
  ./voice/run.sh smoke
  ./voice/run.sh tts "Text"
  WHISPER_MODEL=tiny ./voice/run.sh loop --reply echo|llama|static

Notes:
  - No sudo, no apt.
  - Uses voice/.venv internally; no manual source needed.
  - Piper is the default/stable TTS path.
  - For --reply llama, start ./start_llama_server.sh in another terminal.
USAGE
  exit 1
fi
shift || true

case "$cmd" in
  setup)
    python3 -m venv "$VENV_DIR"
    "$PY" -m pip install -U pip wheel setuptools
    "$PY" -m pip install -r "$VOICE_DIR/requirements.txt"
    "$PY" -m pip install --force-reinstall 'numpy<2'
    PATH="$VENV_DIR/bin:${PATH:-}" PYTHONPATH="$VOICE_DIR:$ROOT_DIR:${PYTHONPATH:-}" \
      "$PY" "$VOICE_DIR/voice_app.py" smoke
    ;;

  download-piper|download)
    if [[ ! -x "$PY" ]]; then
      echo "Fehler: venv fehlt. Erst ausführen: ./voice/run.sh setup" >&2
      exit 1
    fi
    PATH="$VENV_DIR/bin:${PATH:-}" PYTHONPATH="$VOICE_DIR:$ROOT_DIR:${PYTHONPATH:-}" \
      "$PY" "$VOICE_DIR/voice_app.py" download-piper "$@"
    ;;

  smoke|tts|loop)
    if [[ ! -x "$PY" ]]; then
      echo "Fehler: venv fehlt. Erst ausführen: ./voice/run.sh setup" >&2
      exit 1
    fi
    PATH="$VENV_DIR/bin:${PATH:-}" PYTHONPATH="$VOICE_DIR:$ROOT_DIR:${PYTHONPATH:-}" \
      "$PY" "$VOICE_DIR/voice_app.py" "$cmd" "$@"
    ;;

  *)
    echo "Unbekannter Befehl: $cmd" >&2
    echo "Siehe: ./voice/run.sh" >&2
    exit 2
    ;;
esac
