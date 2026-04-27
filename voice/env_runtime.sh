#!/usr/bin/env bash
# Runtime environment for this repo.
# Intended to be sourced by wrapper scripts, not manually.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export ROCM_PATH="${ROCM_PATH:-/opt/rocm}"
export ROCM_HOME="${ROCM_HOME:-$ROCM_PATH}"
export HIP_PATH="${HIP_PATH:-$ROCM_PATH}"
export HSA_PATH="${HSA_PATH:-$ROCM_PATH}"
export HIP_PLATFORM="${HIP_PLATFORM:-amd}"
export HSA_OVERRIDE_GFX_VERSION="${HSA_OVERRIDE_GFX_VERSION:-10.3.0}"

export PATH="$ROCM_PATH/bin:$ROCM_PATH/lib/llvm/bin:$ROCM_PATH/llvm/bin:${PATH:-}"

export LD_LIBRARY_PATH="$ROOT_DIR/llama.cpp/build/bin:$ROCM_PATH/lib:$ROCM_PATH/lib64:$ROCM_PATH/lib/host-math/lib:$ROCM_PATH/lib/rocm_sysdeps/lib:$ROCM_PATH/lib/llvm/lib:$ROCM_PATH/llvm/lib:${LD_LIBRARY_PATH:-}"

# Custom ROCm PyTorch wheel needs libomp for __kmpc_* symbols.
if [[ -e "$ROCM_PATH/lib/llvm/lib/libomp.so" ]]; then
  case ":${LD_PRELOAD:-}:" in
    *":$ROCM_PATH/lib/llvm/lib/libomp.so:"*) ;;
    *) export LD_PRELOAD="$ROCM_PATH/lib/llvm/lib/libomp.so${LD_PRELOAD:+:$LD_PRELOAD}" ;;
  esac
fi

# ggml/ROCm workarounds; harmless for CPU/Piper path.
export GGML_CUDA_DISABLE_FUSION="${GGML_CUDA_DISABLE_FUSION:-1}"
export GGML_CUDA_DISABLE_GRAPHS="${GGML_CUDA_DISABLE_GRAPHS:-1}"
unset GGML_CUDA_GRAPH_OPT
