#!/usr/bin/env bash

# Repo-local caches. Source this from entrypoint scripts before Python/HF tools run.
ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"

export HF_HOME="${HF_HOME:-$ROOT_DIR/.cache/huggingface}"
export HF_HUB_CACHE="${HF_HUB_CACHE:-$HF_HOME/hub}"
export TRANSFORMERS_CACHE="${TRANSFORMERS_CACHE:-$HF_HOME/transformers}"
export HUGGINGFACE_HUB_CACHE="${HUGGINGFACE_HUB_CACHE:-$HF_HUB_CACHE}"
export HF_XET_CACHE="${HF_XET_CACHE:-$HF_HOME/xet}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$ROOT_DIR/.cache/xdg}"
export LLAMA_CACHE="${LLAMA_CACHE:-$ROOT_DIR/.cache/llama.cpp}"

mkdir -p "$HF_HUB_CACHE" "$TRANSFORMERS_CACHE" "$HF_XET_CACHE" "$XDG_CACHE_HOME" "$LLAMA_CACHE"
