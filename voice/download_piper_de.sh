#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VOICE_DIR="$ROOT_DIR/voice"
PY="$VOICE_DIR/.venv/bin/python3"

if [[ ! -x "$PY" ]]; then
  echo "Fehler: venv fehlt. Erst ausführen:" >&2
  echo "  ./voice/setup_piper_env.sh" >&2
  exit 1
fi

PIPER_VOICE="${PIPER_VOICE:-de_DE-thorsten-medium}"
MODEL_DIR="${PIPER_MODEL_DIR:-$VOICE_DIR/models/piper}"
mkdir -p "$MODEL_DIR"

"$PY" - <<PY
from pathlib import Path
from huggingface_hub import hf_hub_download
import os

voice = os.environ.get("PIPER_VOICE", "de_DE-thorsten-medium")
model_dir = Path(os.environ.get("PIPER_MODEL_DIR", "$MODEL_DIR"))
model_dir.mkdir(parents=True, exist_ok=True)

voice_to_path = {
    "de_DE-thorsten-medium": "de/de_DE/thorsten/medium/de_DE-thorsten-medium",
    "de_DE-thorsten-high": "de/de_DE/thorsten/high/de_DE-thorsten-high",
    "de_DE-thorsten-low": "de/de_DE/thorsten/low/de_DE-thorsten-low",
    "de_DE-ramona-low": "de/de_DE/ramona/low/de_DE-ramona-low",
}

stem = voice_to_path.get(voice)
if stem is None:
    raise SystemExit(f"Unbekannte Stimme: {voice}")

repo = "rhasspy/piper-voices"
onnx_name = f"{stem}.onnx"
json_name = f"{stem}.onnx.json"

onnx = hf_hub_download(repo_id=repo, filename=onnx_name, local_dir=model_dir)
cfg = hf_hub_download(repo_id=repo, filename=json_name, local_dir=model_dir)

print("PIPER_MODEL=" + onnx)
print("PIPER_CONFIG=" + cfg)
PY
