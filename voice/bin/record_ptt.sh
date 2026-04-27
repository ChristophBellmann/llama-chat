#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CONFIG="$REPO_ROOT/voice/config.yaml"
RUNTIME_DIR="$REPO_ROOT/voice/runtime"
IN_WAV="$RUNTIME_DIR/in.wav"

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
a = cfg.get('audio', {})
vals = {
  'VOICE_BACKEND': a.get('backend', 'pipewire'),
  'VOICE_INPUT_DEVICE': a.get('input_device', ''),
  'VOICE_SAMPLE_RATE': int(a.get('sample_rate', 16000)),
  'VOICE_CHANNELS': int(a.get('channels', 1)),
  'VOICE_MAX_RECORD_SECONDS': int(a.get('max_record_seconds', 12)),
}
for k, v in vals.items():
    print(f"{k}={shlex.quote(str(v))}")
PY
)"

if [[ "$VOICE_BACKEND" == "pipewire" ]]; then
  if ! command -v pw-record >/dev/null 2>&1; then
    echo "Fehler: pw-record nicht gefunden. Installiere pipewire-utils." >&2
    exit 1
  fi
elif [[ "$VOICE_BACKEND" == "alsa" ]]; then
  if ! command -v arecord >/dev/null 2>&1; then
    echo "Fehler: arecord nicht gefunden." >&2
    exit 1
  fi
else
  echo "Fehler: audio.backend muss 'pipewire' oder 'alsa' sein (aktuell: $VOICE_BACKEND)" >&2
  exit 1
fi

echo "Enter = start recording"
read -r

rm -f "$IN_WAV"
if [[ "$VOICE_BACKEND" == "pipewire" ]]; then
  REC_CMD=(pw-record --rate "$VOICE_SAMPLE_RATE" --channels "$VOICE_CHANNELS")
  if [[ -n "${VOICE_INPUT_DEVICE// }" ]]; then
    REC_CMD+=(--target "$VOICE_INPUT_DEVICE")
  fi
  REC_CMD+=("$IN_WAV")
else
  ALSA_DEV="${VOICE_INPUT_DEVICE:-default}"
  REC_CMD=(arecord -q -D "$ALSA_DEV" -f S16_LE -r "$VOICE_SAMPLE_RATE" -c "$VOICE_CHANNELS" "$IN_WAV")
fi

"${REC_CMD[@]}" &
REC_PID=$!

echo "Enter = stop recording (Auto-Stop nach ${VOICE_MAX_RECORD_SECONDS}s)"
(
  sleep "$VOICE_MAX_RECORD_SECONDS"
  if kill -0 "$REC_PID" 2>/dev/null; then
    kill "$REC_PID" 2>/dev/null || true
  fi
) &
WATCH_PID=$!

while kill -0 "$REC_PID" 2>/dev/null; do
  if read -r -t 0.2 _; then
    kill "$REC_PID" 2>/dev/null || true
    break
  fi
done

wait "$REC_PID" 2>/dev/null || true
kill "$WATCH_PID" 2>/dev/null || true
wait "$WATCH_PID" 2>/dev/null || true

if [[ ! -s "$IN_WAV" ]]; then
  echo "Hinweis: Keine gueltige Aufnahme erzeugt." >&2
  exit 0
fi

echo "Aufnahme gespeichert: $IN_WAV"
