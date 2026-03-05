#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CONFIG="$REPO_ROOT/voice/config.yaml"
OUT_WAV="$REPO_ROOT/voice/runtime/out.wav"

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
  'VOICE_OUTPUT_DEVICE': a.get('output_device', ''),
}
for k, v in vals.items():
    print(f"{k}={shlex.quote(str(v))}")
PY
)"

if [[ ! -s "$OUT_WAV" ]]; then
  echo "Hinweis: Keine Audioausgabe vorhanden: $OUT_WAV"
  exit 0
fi

if [[ "$VOICE_BACKEND" == "pipewire" ]]; then
  if ! command -v pw-play >/dev/null 2>&1; then
    echo "Fehler: pw-play nicht gefunden. Installiere pipewire-utils." >&2
    exit 1
  fi
  PLAY_CMD=(pw-play)
  if [[ -n "${VOICE_OUTPUT_DEVICE// }" ]]; then
    PLAY_CMD+=(--target "$VOICE_OUTPUT_DEVICE")
  fi
  PLAY_CMD+=("$OUT_WAV")
  "${PLAY_CMD[@]}"
elif [[ "$VOICE_BACKEND" == "alsa" ]]; then
  if ! command -v aplay >/dev/null 2>&1; then
    echo "Fehler: aplay nicht gefunden." >&2
    exit 1
  fi
  ALSA_DEV="${VOICE_OUTPUT_DEVICE:-default}"
  aplay -q -D "$ALSA_DEV" "$OUT_WAV"
else
  echo "Fehler: audio.backend muss 'pipewire' oder 'alsa' sein (aktuell: $VOICE_BACKEND)" >&2
  exit 1
fi
