#!/usr/bin/env bash
set -euo pipefail

# Full setup:
# - Piper default stack
# - Optional custom ROCm Torch + SNAC stack for Orpheus experiments
#
# No sudo, no apt, no ROCm package download.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VOICE_DIR="$ROOT_DIR/voice"
VENV_DIR="${VENV_DIR:-$VOICE_DIR/.venv}"
PY="$VENV_DIR/bin/python3"

"$VOICE_DIR/setup_piper_env.sh"

source "$VOICE_DIR/env_runtime.sh"

TORCH_WHEEL="${TORCH_WHEEL:-/opt/rocm/wheels/pytorch_rocm711/torch-current.whl}"
TORCHAUDIO_WHEEL="${TORCHAUDIO_WHEEL:-/opt/rocm/wheels/pytorch_rocm711/torchaudio-current.whl}"
TORCHCODEC_WHEEL="${TORCHCODEC_WHEEL:-/opt/rocm/wheels/pytorch_rocm711/torchcodec-current.whl}"

if [[ -e "$TORCH_WHEEL" ]]; then
  TORCH_WHEEL="$(readlink -f "$TORCH_WHEEL")"
  echo "Installiere Custom Torch:"
  echo "  $TORCH_WHEEL"
  "$PY" -m pip install --force-reinstall "$TORCH_WHEEL"

  if [[ -e "$TORCHAUDIO_WHEEL" ]]; then
    "$PY" -m pip install --force-reinstall "$(readlink -f "$TORCHAUDIO_WHEEL")" || true
  fi

  if [[ -e "$TORCHCODEC_WHEEL" ]]; then
    "$PY" -m pip install --force-reinstall "$(readlink -f "$TORCHCODEC_WHEEL")" || true
  fi

  "$PY" -m pip install snac
  "$PY" -m pip install --force-reinstall "numpy<2"

  "$PY" - <<'PY'
import numpy
import torch
import snac
print("numpy:", numpy.__version__)
print("torch:", torch.__version__)
print("torch.version.rocm:", getattr(torch.version, "rocm", None))
print("torch.version.hip:", getattr(torch.version, "hip", None))
print("torch.cuda.is_available:", torch.cuda.is_available())
print("snac: OK")
PY
else
  echo "Hinweis: kein Torch-Wheel gefunden: $TORCH_WHEEL"
  echo "Orpheus/SNAC wird nicht eingerichtet. Piper funktioniert trotzdem."
fi
