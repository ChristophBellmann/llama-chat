#!/usr/bin/env bash
set -euo pipefail

# Erstellt .txt-Transkripte für alle .wav-Dateien in einem Ordner
# mittels OpenAI Whisper (tiny, deutsch).
#
# Nutzung:
#   ./voice/transcribe.sh               # transkribiert alle voices/*.wav
#   ./voice/transcribe.sh /pfad/zu/wavs # transkribiert in benutzerdefiniertem Ordner

DIR="${1:-$(dirname "$0")/../voices}"
DIR="$(realpath "$DIR")"

if ! command -v whisper &>/dev/null; then
  echo "whisper nicht gefunden. Installiere openai-whisper..."
  pip install --break-system-packages -q openai-whisper
fi

cd "$DIR"
for wav in *.wav; do
  [ -f "$wav" ] || continue
  base="${wav%.wav}"
  [ -f "$base.txt" ] && echo "  existiert: $base.txt" && continue
  echo "  transkribiere: $wav"
  whisper "$wav" --model tiny --language de --output_format txt --output_dir "$DIR" 2>/dev/null
done

echo "Fertig: $(ls -1 "$DIR"/*.txt 2>/dev/null | wc -l) Transkripte in $DIR"
