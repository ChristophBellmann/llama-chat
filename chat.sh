#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LLAMA_DIR="$ROOT_DIR/llama.cpp"
MODEL_PATH="${1:-$ROOT_DIR/models/Qwen3.5-9B-Q4_K_M.gguf}"

if [[ ! -x "$LLAMA_DIR/build/bin/llama-cli" ]]; then
  echo "Fehler: llama-cli nicht gefunden unter $LLAMA_DIR/build/bin/llama-cli"
  echo "Bitte zuerst bauen:"
  echo "  cd $LLAMA_DIR"
  echo "  export PATH=/opt/rocm/bin:$PATH"
  echo "  export HIP_PLATFORM=amd"
  echo "  cmake -S . -B build -G Ninja -DGGML_HIP=ON -DCMAKE_PREFIX_PATH=/opt/rocm -DHIP_PLATFORM=amd -DAMDGPU_TARGETS=gfx1031"
  echo "  cmake --build build -j"
  exit 1
fi

if [[ ! -f "$MODEL_PATH" ]]; then
  echo "Fehler: Modell nicht gefunden: $MODEL_PATH"
  echo "Download-Beispiel:"
  echo "  cd $ROOT_DIR/models"
  echo "  wget -c https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main/Qwen3.5-9B-Q4_K_M.gguf"
  exit 1
fi

export PATH="/opt/rocm/bin:$PATH"
export LD_LIBRARY_PATH="/opt/rocm/lib:/opt/rocm/lib64:${LD_LIBRARY_PATH:-}"
export HIP_PLATFORM=amd

exec "$LLAMA_DIR/build/bin/llama-cli" \
  --model "$MODEL_PATH" \
  --gpu-layers 99 \
  --ctx-size 2048 \
  --threads "$(nproc)" \
  --prio 2 \
  --temp 0.7 \
  --top-p 0.9 \
  --conversation
