#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CONFIG="$REPO_ROOT/voice/config.yaml"
RUNTIME_DIR="$REPO_ROOT/voice/runtime"
OUT_TXT="$RUNTIME_DIR/out.txt"
OUT_WAV="$RUNTIME_DIR/out.wav"

mkdir -p "$RUNTIME_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Fehler: python3 nicht gefunden." >&2
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
t = cfg.get('tts', {})
vals = {
  'PIPER_BIN': t.get('piper_bin', 'piper'),
  'PIPER_MODEL': t.get('model_path', './third_party/piper/de_DE-voice.onnx'),
}
for k, v in vals.items():
    print(f"{k}={shlex.quote(str(v))}")
PY
)"

if [[ "$PIPER_MODEL" == ./* ]]; then
  PIPER_MODEL="$REPO_ROOT/${PIPER_MODEL#./}"
fi

if ! command -v "$PIPER_BIN" >/dev/null 2>&1; then
  echo "Fehler: piper nicht gefunden: $PIPER_BIN" >&2
  exit 1
fi
if [[ ! -f "$PIPER_MODEL" ]]; then
  echo "Fehler: Piper Modell nicht gefunden: $PIPER_MODEL" >&2
  exit 1
fi

TEXT=""
if [[ -f "$OUT_TXT" ]]; then
  TEXT="$(cat "$OUT_TXT")"
fi
if [[ -z "${TEXT// }" ]]; then
  : > "$OUT_WAV"
  echo "Hinweis: Kein Text fuer TTS vorhanden."
  exit 0
fi

echo "$TEXT" | "$PIPER_BIN" --model "$PIPER_MODEL" --output_file "$OUT_WAV" >/dev/null 2>&1

echo "TTS WAV erstellt: $OUT_WAV"
