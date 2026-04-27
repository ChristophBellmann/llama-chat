#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VOICE_DIR="$ROOT_DIR/voice"
VENV_DIR="${VENV_DIR:-$VOICE_DIR/.venv}"

python3 -m venv "$VENV_DIR"
PY="$VENV_DIR/bin/python3"

"$PY" -m pip install -U pip wheel setuptools
"$PY" -m pip install -r "$VOICE_DIR/requirements_piper.txt"
"$PY" -m pip install --force-reinstall "numpy<2"

"$PY" - <<'PY'
import importlib
for mod in ["numpy", "sounddevice", "faster_whisper", "requests", "huggingface_hub"]:
    importlib.import_module(mod)
    print(f"OK import {mod}")

import shutil
print("piper executable:", shutil.which("piper"))
PY

cat <<MSG

OK: Piper/Voice-Umgebung erstellt:
  $VENV_DIR

Modell laden:
  ./voice/download_piper_de.sh

TTS:
  ./voice/run_tts.sh "Die Haustür ist noch offen."

Voice Loop:
  WHISPER_MODEL=tiny ./voice/run_voice_loop.sh --reply echo
MSG
