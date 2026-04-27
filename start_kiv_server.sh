#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIV_DIR="$ROOT_DIR/kiv"
VENV="$KIV_DIR/.venv-kiv"

MODEL="${1:-${KIV_MODEL:-google/gemma-4-E2B-it}}"
HOST="${KIV_HOST:-127.0.0.1}"
PORT="${KIV_PORT:-11435}"
DEVICE_MAP="${KIV_DEVICE_MAP:-auto}"
DTYPE="${KIV_DTYPE:-float16}"
LOG_LEVEL="${KIV_LOG_LEVEL:-INFO}"
ROCM_ROOT="${ROCM_PATH:-/opt/rocm}"

if [[ ! -d "$KIV_DIR" ]]; then
  echo "Fehler: $KIV_DIR nicht gefunden" >&2
  exit 1
fi

if [[ ! -f "$VENV/bin/activate" ]]; then
  echo "Fehler: KIV venv fehlt unter $VENV" >&2
  echo "Installiere zuerst KIV (siehe README im Ordner $KIV_DIR)." >&2
  exit 1
fi

source "$VENV/bin/activate"
export LD_LIBRARY_PATH="${ROCM_ROOT}/lib/llvm/lib:${ROCM_ROOT}/lib:${LD_LIBRARY_PATH:-}"

echo "Starte KIV"
echo "  model:      $MODEL"
echo "  endpoint:   http://$HOST:$PORT"
echo "  device-map: $DEVICE_MAP"
echo "  dtype:      $DTYPE"
echo "  rocm-root:  $ROCM_ROOT"

exec kiv serve \
  --model "$MODEL" \
  --host "$HOST" \
  --port "$PORT" \
  --device-map "$DEVICE_MAP" \
  --dtype "$DTYPE" \
  --log-level "$LOG_LEVEL"
