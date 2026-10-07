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
# HIP-Graph-Capture zeigte beim Wechsel zwischen residenten Modellen lange
# Pausen vor dem ersten Audiotoken. Gleicher Workaround wie beim Chatserver.
export GGML_CUDA_DISABLE_GRAPHS="${GGML_CUDA_DISABLE_GRAPHS:-1}"

exec ./start_voice_server.sh "$MODEL"
