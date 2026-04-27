#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL="${1:-qwen35-local}"

"$ROOT_DIR/start_ollama.sh"

export OLLAMA_HOST="http://127.0.0.1:11434"
export OLLAMA_MODELS="$ROOT_DIR/ollama-models"
export LD_LIBRARY_PATH="/opt/rocm/lib:/opt/rocm/lib64:${LD_LIBRARY_PATH:-}"
export HIP_VISIBLE_DEVICES="0"
export HSA_OVERRIDE_GFX_VERSION="10.3.0"

exec "$ROOT_DIR/chat_ollama_files.py" "$MODEL"
