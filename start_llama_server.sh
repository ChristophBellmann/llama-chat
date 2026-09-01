#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$ROOT_DIR/env.local.sh"
# Build-Verzeichnis. Standard ist b10741 -- zwingend fuer gemma-4 (arch "gemma4")
# und Dirk-Qwen3.8-27B (MTP-Layer). Der alte Build (Tag working-2026-03-04)
# kennt beide nicht und ist als Rueckfallebene weiter da:
#   LLAMA_BIN_DIR="$ROOT_DIR/llama.cpp/build/bin" ./start_llama_server.sh
BIN_DIR="${LLAMA_BIN_DIR:-$ROOT_DIR/llama.cpp-b10741/build/bin}"
# Dieses Skript ist der ExecStart der systemd-Unit llama-server.service und
# damit das Produktiv-LLM fuer Home Assistant (Alias locales_llm, Primary des
# llm-routers auf thinkthing). Modellwechsel hier sind Produktivaenderungen.
# Ueberschreibbar per Env, damit die Unit ein Modell festnageln kann, ohne dass
# das Textchat-Profil in profiles/default.ini es mitzieht:
#   systemctl --user set-environment MODEL_PATH=...   oder Drop-in mit Environment=
MODEL_PATH="${MODEL_PATH:-$ROOT_DIR/models/gemma-4-12B-it-qat-UD-Q4_K_XL.gguf}"
MODEL_ALIAS="${MODEL_ALIAS:-locales_llm}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8080}"
CTX="${CTX:-32768}"
GPU_LAYERS="${GPU_LAYERS:--1}"
CACHE_TYPE_K="${CACHE_TYPE_K:-q8_0}"
CACHE_TYPE_V="${CACHE_TYPE_V:-q8_0}"
FLASH_ATTN="${FLASH_ATTN:-on}"
BATCH_SIZE="${BATCH_SIZE:-2048}"
UBATCH_SIZE="${UBATCH_SIZE:-512}"
PARALLEL="${PARALLEL:-2}"
REASONING_BUDGET="${REASONING_BUDGET:-0}"
# --reasoning-budget ist bei den qwen35-Modellen wirkungslos (getestet auf b10741:
# 5,2 s mit und ohne, content teils leer). Nur das hier schaltet Thinking wirklich ab.
CHAT_TEMPLATE_KWARGS="${CHAT_TEMPLATE_KWARGS:-{\"enable_thinking\":false\}}"
LONG_CONTEXT="${LONG_CONTEXT:-0}"
ROPE_SCALING="${ROPE_SCALING:-yarn}"
ROPE_SCALE="${ROPE_SCALE:-2.0}"
YARN_ORIG_CTX="${YARN_ORIG_CTX:-0}"
YARN_EXT_FACTOR="${YARN_EXT_FACTOR:--1.0}"
YARN_ATTN_FACTOR="${YARN_ATTN_FACTOR:--1.0}"
YARN_BETA_SLOW="${YARN_BETA_SLOW:--1.0}"
YARN_BETA_FAST="${YARN_BETA_FAST:--1.0}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      [[ $# -ge 2 ]] || { echo "Fehler: --host erwartet einen Wert" >&2; exit 1; }
      HOST="$2"
      shift 2
      ;;
    --port)
      [[ $# -ge 2 ]] || { echo "Fehler: --port erwartet einen Wert" >&2; exit 1; }
      PORT="$2"
      shift 2
      ;;
    --alias)
      [[ $# -ge 2 ]] || { echo "Fehler: --alias erwartet einen Wert" >&2; exit 1; }
      MODEL_ALIAS="$2"
      shift 2
      ;;
    --ctx)
      [[ $# -ge 2 ]] || { echo "Fehler: --ctx erwartet einen Wert" >&2; exit 1; }
      CTX="$2"
      shift 2
      ;;
    --ngl)
      [[ $# -ge 2 ]] || { echo "Fehler: --ngl erwartet einen Wert" >&2; exit 1; }
      GPU_LAYERS="$2"
      shift 2
      ;;
    --ctk)
      [[ $# -ge 2 ]] || { echo "Fehler: --ctk erwartet einen Wert" >&2; exit 1; }
      CACHE_TYPE_K="$2"
      shift 2
      ;;
    --ctv)
      [[ $# -ge 2 ]] || { echo "Fehler: --ctv erwartet einen Wert" >&2; exit 1; }
      CACHE_TYPE_V="$2"
      shift 2
      ;;
    --long-context)
      [[ $# -ge 2 ]] || { echo "Fehler: --long-context erwartet 0 oder 1" >&2; exit 1; }
      LONG_CONTEXT="$2"
      shift 2
      ;;
    --rope-scaling)
      [[ $# -ge 2 ]] || { echo "Fehler: --rope-scaling erwartet einen Wert" >&2; exit 1; }
      ROPE_SCALING="$2"
      shift 2
      ;;
    --rope-scale)
      [[ $# -ge 2 ]] || { echo "Fehler: --rope-scale erwartet einen Wert" >&2; exit 1; }
      ROPE_SCALE="$2"
      shift 2
      ;;
    --yarn-orig-ctx)
      [[ $# -ge 2 ]] || { echo "Fehler: --yarn-orig-ctx erwartet einen Wert" >&2; exit 1; }
      YARN_ORIG_CTX="$2"
      shift 2
      ;;
    --yarn-ext-factor)
      [[ $# -ge 2 ]] || { echo "Fehler: --yarn-ext-factor erwartet einen Wert" >&2; exit 1; }
      YARN_EXT_FACTOR="$2"
      shift 2
      ;;
    --yarn-attn-factor)
      [[ $# -ge 2 ]] || { echo "Fehler: --yarn-attn-factor erwartet einen Wert" >&2; exit 1; }
      YARN_ATTN_FACTOR="$2"
      shift 2
      ;;
    --yarn-beta-slow)
      [[ $# -ge 2 ]] || { echo "Fehler: --yarn-beta-slow erwartet einen Wert" >&2; exit 1; }
      YARN_BETA_SLOW="$2"
      shift 2
      ;;
    --yarn-beta-fast)
      [[ $# -ge 2 ]] || { echo "Fehler: --yarn-beta-fast erwartet einen Wert" >&2; exit 1; }
      YARN_BETA_FAST="$2"
      shift 2
      ;;
    --fa|--flash-attn)
      [[ $# -ge 2 ]] || { echo "Fehler: --flash-attn erwartet on/off/auto" >&2; exit 1; }
      FLASH_ATTN="$2"
      shift 2
      ;;
    --batch-size)
      [[ $# -ge 2 ]] || { echo "Fehler: --batch-size erwartet einen Wert" >&2; exit 1; }
      BATCH_SIZE="$2"
      shift 2
      ;;
    --ubatch-size)
      [[ $# -ge 2 ]] || { echo "Fehler: --ubatch-size erwartet einen Wert" >&2; exit 1; }
      UBATCH_SIZE="$2"
      shift 2
      ;;
    --parallel)
      [[ $# -ge 2 ]] || { echo "Fehler: --parallel erwartet einen Wert" >&2; exit 1; }
      PARALLEL="$2"
      shift 2
      ;;
    --reasoning-budget)
      [[ $# -ge 2 ]] || { echo "Fehler: --reasoning-budget erwartet 0 oder -1" >&2; exit 1; }
      REASONING_BUDGET="$2"
      shift 2
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "Fehler: Unbekannte Option: $1" >&2
      exit 1
      ;;
    *)
      MODEL_PATH="$1"
      shift
      ;;
  esac
done

if [[ ! -x "$BIN_DIR/llama-server" ]]; then
  echo "Fehler: llama-server nicht gefunden unter $BIN_DIR/llama-server" >&2
  exit 1
fi

if [[ ! -f "$MODEL_PATH" ]]; then
  echo "Fehler: Modell nicht gefunden: $MODEL_PATH" >&2
  echo "Nutze: $0 /absoluter/pfad/zum/model.gguf" >&2
  exit 1
fi

export LD_LIBRARY_PATH="$BIN_DIR:${LD_LIBRARY_PATH:-}"

echo "Starte llama-server"
echo "  model: $MODEL_PATH"
echo "  alias: $MODEL_ALIAS"
echo "  url:   http://$HOST:$PORT/v1"
echo "  ctx:   $CTX"
echo "  ngl:   $GPU_LAYERS"
echo "  fa:    $FLASH_ATTN"
echo "  batch: $BATCH_SIZE / $UBATCH_SIZE"
echo "  slots: $PARALLEL"
echo "  think: $CHAT_TEMPLATE_KWARGS"
echo "  (--reasoning-budget $REASONING_BUDGET wirkt nur bei gemma, nicht bei qwen35)"
echo "  slot ctx: $((CTX / PARALLEL))"
echo "  ctk:   $CACHE_TYPE_K"
echo "  ctv:   $CACHE_TYPE_V"
echo "  long:  $LONG_CONTEXT"
if [[ "$LONG_CONTEXT" == "1" ]]; then
  echo "  rope:  $ROPE_SCALING (scale=$ROPE_SCALE)"
fi
ARGS=(
  -m "$MODEL_PATH"
  --alias "$MODEL_ALIAS"
  --host "$HOST"
  --port "$PORT"
  -ngl "$GPU_LAYERS"
  -c "$CTX"
  --flash-attn "$FLASH_ATTN"
  --batch-size "$BATCH_SIZE"
  --ubatch-size "$UBATCH_SIZE"
  -ctk "$CACHE_TYPE_K"
  -ctv "$CACHE_TYPE_V"
  --jinja
  --parallel "$PARALLEL"
  --reasoning-budget "$REASONING_BUDGET"
  --chat-template-kwargs "$CHAT_TEMPLATE_KWARGS"
)

if [[ "$LONG_CONTEXT" == "1" ]]; then
  ARGS+=(
    --rope-scaling "$ROPE_SCALING"
    --rope-scale "$ROPE_SCALE"
    --yarn-orig-ctx "$YARN_ORIG_CTX"
    --yarn-ext-factor "$YARN_EXT_FACTOR"
    --yarn-attn-factor "$YARN_ATTN_FACTOR"
    --yarn-beta-slow "$YARN_BETA_SLOW"
    --yarn-beta-fast "$YARN_BETA_FAST"
  )
fi

exec "$BIN_DIR/llama-server" "${ARGS[@]}"
