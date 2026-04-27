#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VOICE_DIR="$ROOT_DIR/voice"
PY="$VOICE_DIR/.venv/bin/python3"

if [[ ! -x "$PY" ]]; then
  echo "Fehler: venv fehlt. Erst ausführen: ./voice/setup_voice_env.sh" >&2
  exit 1
fi

"$PY" - <<'PY'
from huggingface_hub import hf_hub_download

path = hf_hub_download(
    repo_id="freddyaboulton/3b-de-ft-research_release-Q4_K_M-GGUF",
    filename="3b-de-ft-research_release-q4_k_m.gguf",
)
print(path)
PY
