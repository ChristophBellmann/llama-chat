#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

MODEL="$(./voice/run.sh orpheus-path)"

export HSA_OVERRIDE_GFX_VERSION="${HSA_OVERRIDE_GFX_VERSION:-10.3.1}"
export PORT="${PORT:-8082}"
export MODEL_ALIAS="${MODEL_ALIAS:-orpheus-tts}"
export CTX="${CTX:-4096}"
export GPU_LAYERS="${GPU_LAYERS:--1}"
export PARALLEL="${PARALLEL:-1}"

exec ./start_voice_server.sh "$MODEL"
