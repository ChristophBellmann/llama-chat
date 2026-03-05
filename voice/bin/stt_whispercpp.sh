#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CONFIG="$REPO_ROOT/voice/config.yaml"
RUNTIME_DIR="$REPO_ROOT/voice/runtime"
IN_WAV="$RUNTIME_DIR/in.wav"
IN_16K="$RUNTIME_DIR/in_16k.wav"
IN_TXT="$RUNTIME_DIR/in.txt"

mkdir -p "$RUNTIME_DIR"

if [[ ! -f "$IN_WAV" ]]; then
  echo "Fehler: Aufnahme fehlt: $IN_WAV" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Fehler: python3 nicht gefunden." >&2
  exit 1
fi
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "Fehler: ffmpeg nicht gefunden." >&2
  exit 1
fi

eval "$(python3 - "$CONFIG" <<'PY'
import shlex, sys
try:
    import yaml
except Exception:
    print('echo "Fehler: PyYAML fehlt. Installiere mit: pip install pyyaml" >&2')
    print('exit 1')
    raise SystemExit
cfg = yaml.safe_load(open(sys.argv[1], encoding='utf-8'))
s = cfg.get('stt', {})
vals = {
  'WHISPER_BIN': s.get('whispercpp_bin', './third_party/whisper.cpp/whisper-cli'),
  'WHISPER_MODEL': s.get('model_path', './third_party/whisper.cpp/models/ggml-small.bin'),
  'WHISPER_LANG': s.get('lang', 'de'),
}
for k, v in vals.items():
    print(f"{k}={shlex.quote(str(v))}")
PY
)"

if [[ "$WHISPER_BIN" == ./* ]]; then
  WHISPER_BIN="$REPO_ROOT/${WHISPER_BIN#./}"
fi
if [[ "$WHISPER_MODEL" == ./* ]]; then
  WHISPER_MODEL="$REPO_ROOT/${WHISPER_MODEL#./}"
fi

# Fallback: falls konfiguriertes Binary fehlt, probiere whisper-cli im PATH.
if [[ ! -x "$WHISPER_BIN" ]]; then
  if command -v whisper-cli >/dev/null 2>&1; then
    WHISPER_BIN="$(command -v whisper-cli)"
  fi
fi

if [[ ! -x "$WHISPER_BIN" ]]; then
  cat >&2 <<EOF
Fehler: whisper.cpp binary nicht ausfuehrbar: $WHISPER_BIN

Loesung (Beispiel):
  cd "$REPO_ROOT"
  git clone https://github.com/ggml-org/whisper.cpp third_party/whisper.cpp
  cmake -S third_party/whisper.cpp -B third_party/whisper.cpp/build -G Ninja
  cmake --build third_party/whisper.cpp/build -j
  # dann in voice/config.yaml setzen:
  # stt.whispercpp_bin: "./third_party/whisper.cpp/build/bin/whisper-cli"
EOF
  exit 1
fi
if [[ ! -f "$WHISPER_MODEL" ]]; then
  cat >&2 <<EOF
Fehler: whisper model nicht gefunden: $WHISPER_MODEL

Beispiel-Download:
  mkdir -p "$REPO_ROOT/third_party/whisper.cpp/models"
  cd "$REPO_ROOT/third_party/whisper.cpp/models"
  wget -c https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin
EOF
  exit 1
fi

ffmpeg -y -i "$IN_WAV" -ac 1 -ar 16000 "$IN_16K" >/dev/null 2>&1

"$WHISPER_BIN" -m "$WHISPER_MODEL" -f "$IN_16K" -l "$WHISPER_LANG" --output-txt --output-file "$RUNTIME_DIR/in" >/dev/null 2>&1

RAW_TXT="$RUNTIME_DIR/in.txt"
if [[ ! -f "$RAW_TXT" ]]; then
  : > "$IN_TXT"
  exit 0
fi

CLEAN="$(sed -E 's/\[[0-9:.[:space:]-]+\]//g' "$RAW_TXT" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g' | tr '\n' ' ' | sed -E 's/[[:space:]]+/ /g; s/^ //; s/ $//')"
printf '%s\n' "$CLEAN" > "$IN_TXT"

echo "STT: $CLEAN"
