#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/env.local.sh"
VOICE_DIR="$ROOT_DIR/voice"
VENV_DIR="${VENV_DIR:-$VOICE_DIR/.venv}"
PY="$VENV_DIR/bin/python3"

cmd="${1:-}"
if [[ -z "$cmd" ]]; then
  cat <<'USAGE'
Usage:
  ./voice/run.sh setup
  ./voice/run.sh setup-orpheus
  ./voice/run.sh download-piper [voice]
  ./voice/run.sh download-orpheus
  ./voice/run.sh orpheus-path
  ./voice/run.sh smoke
  ./voice/run.sh smoke-orpheus

  ./voice/run.sh tts [--tts piper|orpheus|orpheus-server] "Text"
  WHISPER_MODEL=small ./voice/run.sh loop --reply echo|llama|static [--tts piper|orpheus|orpheus-server]

Notes:
  - No sudo, no apt.
  - Uses voice/.venv internally; no manual source needed.
  - Stable default: Piper.
  - Orpheus speech is optional/experimental.
USAGE
  exit 1
fi
shift || true

runtime_env() {
  export PYTHONPATH="$VOICE_DIR:$ROOT_DIR:${PYTHONPATH:-}"
  export SNAC_DEVICE="${SNAC_DEVICE:-cpu}"
  export PATH="$VENV_DIR/bin:${PATH:-}"

  # Prefer repo-local llama.cpp libs, same principle as start_llama_server.sh.
  export LD_LIBRARY_PATH="$ROOT_DIR/llama.cpp/build/bin:${LD_LIBRARY_PATH:-}"

  # Optional ROCm runtime for custom Torch/SNAC imports. Harmless if unused.
  if [[ -d /opt/rocm ]]; then
    export ROCM_PATH="${ROCM_PATH:-/opt/rocm}"
    export ROCM_HOME="${ROCM_HOME:-$ROCM_PATH}"
    export HIP_PATH="${HIP_PATH:-$ROCM_PATH}"
    export HSA_PATH="${HSA_PATH:-$ROCM_PATH}"
    export HIP_PLATFORM="${HIP_PLATFORM:-amd}"
    export HSA_OVERRIDE_GFX_VERSION="${HSA_OVERRIDE_GFX_VERSION:-10.3.0}"
    export PATH="$ROCM_PATH/bin:$ROCM_PATH/lib/llvm/bin:$ROCM_PATH/llvm/bin:${PATH:-}"
    export LD_LIBRARY_PATH="$ROOT_DIR/llama.cpp/build/bin:$ROCM_PATH/lib:$ROCM_PATH/lib64:$ROCM_PATH/lib/host-math/lib:$ROCM_PATH/lib/rocm_sysdeps/lib:$ROCM_PATH/lib/llvm/lib:$ROCM_PATH/llvm/lib:${LD_LIBRARY_PATH:-}"
    if [[ -e "$ROCM_PATH/lib/llvm/lib/libomp.so" ]]; then
      case ":${LD_PRELOAD:-}:" in
        *":$ROCM_PATH/lib/llvm/lib/libomp.so:"*) ;;
        *) export LD_PRELOAD="$ROCM_PATH/lib/llvm/lib/libomp.so${LD_PRELOAD:+:$LD_PRELOAD}" ;;
      esac
    fi
  fi
}

ensure_venv() {
  if [[ ! -x "$PY" ]]; then
    echo "Fehler: venv fehlt. Erst ausführen: ./voice/run.sh setup" >&2
    exit 1
  fi
}

case "$cmd" in
  setup)
    python3 -m venv "$VENV_DIR"
    runtime_env
    "$PY" -m pip install -U pip wheel setuptools
    "$PY" -m pip install -r "$VOICE_DIR/requirements.txt"
    "$PY" -m pip install --force-reinstall 'numpy<2'
    "$PY" "$VOICE_DIR/voice_app.py" smoke
    ;;

  setup-orpheus)
    if [[ ! -x "$PY" ]]; then
      python3 -m venv "$VENV_DIR"
    fi
    runtime_env
    "$PY" -m pip install -U pip wheel setuptools

    TORCH_WHEEL="${TORCH_WHEEL:-/opt/rocm/wheels/pytorch_rocm711/torch-current.whl}"
    if [[ -e "$TORCH_WHEEL" ]]; then
      TORCH_WHEEL="$(readlink -f "$TORCH_WHEEL")"
      echo "Installiere lokales Torch-Wheel: $TORCH_WHEEL"
      "$PY" -m pip install --force-reinstall "$TORCH_WHEEL"
    else
      echo "Hinweis: kein lokales Torch-Wheel gefunden: $TORCH_WHEEL" >&2
      echo "snac kann dann ggf. CPU-Torch von PyPI nachziehen." >&2
    fi

    "$PY" -m pip install -r "$VOICE_DIR/requirements.txt"
    "$PY" -m pip install 'snac>=1.2.1' 'numpy<2'
    "$PY" "$VOICE_DIR/voice_app.py" smoke-orpheus
    ;;

  download-piper|download)
    ensure_venv
    runtime_env
    "$PY" "$VOICE_DIR/voice_app.py" download-piper "$@"
    ;;

  download-orpheus|orpheus-path|smoke|smoke-orpheus|tts|loop)
    ensure_venv
    runtime_env
    "$PY" "$VOICE_DIR/voice_app.py" "$cmd" "$@"
    ;;

  *)
    echo "Unbekannter Befehl: $cmd" >&2
    echo "Siehe: ./voice/run.sh" >&2
    exit 2
    ;;
esac
