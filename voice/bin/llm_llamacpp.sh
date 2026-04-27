#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CONFIG="$REPO_ROOT/voice/config.yaml"
RUNTIME_DIR="$REPO_ROOT/voice/runtime"
IN_TXT="$RUNTIME_DIR/in.txt"
OUT_TXT="$RUNTIME_DIR/out.txt"

mkdir -p "$RUNTIME_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Fehler: python3 nicht gefunden." >&2
  exit 1
fi

TRANSCRIPT=""
if [[ -f "$IN_TXT" ]]; then
  TRANSCRIPT="$(cat "$IN_TXT")"
fi
if [[ -z "${TRANSCRIPT// }" ]]; then
  : > "$OUT_TXT"
  exit 0
fi

eval "$(python3 - "$CONFIG" <<'PY'
import shlex, sys
try:
    import yaml
except Exception:
    print('echo "Fehler: PyYAML fehlt. Installiere mit: pip install pyyaml" >&2')
    print('exit 1')
    raise SystemExit
cfg = yaml.safe_load(open(sys.argv[1], encoding='utf-8'))
l = cfg.get('llm', {})
p = cfg.get('prompts', {})
vals = {
  'LLM_BIN': l.get('bin', './llama-cli'),
  'LLM_MODEL': l.get('model_path', './models/Qwen3.5-9B-Q4_K_M.gguf'),
  'LLM_CONTEXT': int(l.get('context', 8192)),
  'LLM_NGL': int(l.get('ngl', 99)),
  'LLM_TEMP': float(l.get('temperature', 0.7)),
  'LLM_TOP_P': float(l.get('top_p', 0.9)),
  'LLM_MAX_TOKENS': int(l.get('max_tokens', 400)),
  'LLM_SYSTEM': p.get('system', ''),
}
for k, v in vals.items():
    print(f"{k}={shlex.quote(str(v))}")
PY
)"

if [[ "$LLM_BIN" == ./* ]]; then
  LLM_BIN="$REPO_ROOT/${LLM_BIN#./}"
fi
if [[ "$LLM_MODEL" == ./* ]]; then
  LLM_MODEL="$REPO_ROOT/${LLM_MODEL#./}"
fi

if [[ ! -x "$LLM_BIN" ]]; then
  FALLBACK="$REPO_ROOT/llama.cpp/build/bin/llama-cli"
  if [[ -x "$FALLBACK" ]]; then
    LLM_BIN="$FALLBACK"
  else
    echo "Fehler: llama-cli nicht gefunden: $LLM_BIN" >&2
    exit 1
  fi
fi
if [[ ! -f "$LLM_MODEL" ]]; then
  echo "Fehler: LLM Modell nicht gefunden: $LLM_MODEL" >&2
  exit 1
fi

PROMPT="$LLM_SYSTEM"
PROMPT+=$'\n\nUser: '
PROMPT+="$TRANSCRIPT"
PROMPT+=$'\nAssistant:'

RAW_OUT="$RUNTIME_DIR/.llm_raw.out"
RAW_ERR="$RUNTIME_DIR/.llm_raw.err"

"$LLM_BIN" \
  --log-disable \
  -m "$LLM_MODEL" \
  -c "$LLM_CONTEXT" \
  -ngl "$LLM_NGL" \
  --temp "$LLM_TEMP" \
  --top-p "$LLM_TOP_P" \
  -n "$LLM_MAX_TOKENS" \
  --no-conversation \
  --prompt "$PROMPT" \
  > "$RAW_OUT" 2> "$RAW_ERR"

CLEAN="$(tr -d '\r' < "$RAW_OUT" | sed -E 's/\x1B\[[0-9;]*[A-Za-z]//g')"
CLEAN="$(printf '%s' "$CLEAN" | sed -E 's/^Assistant:[[:space:]]*//')"
CLEAN="$(printf '%s' "$CLEAN" | sed -E 's/[[:space:]]+$//')"

printf '%s\n' "$CLEAN" > "$OUT_TXT"
echo "LLM Antwort gespeichert: $OUT_TXT"
