#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${TARGET_DIR:-$ROOT_DIR/models}"

MODEL_REPO="${MODEL_REPO:-bartowski/Qwen_Qwen3.6-27B-GGUF}"
MODEL_FILE="${MODEL_FILE:-Qwen_Qwen3.6-27B-Q4_K_M.gguf}"

# Optional canonical filename used by chat.sh defaults.
CANONICAL_LINK_NAME="${CANONICAL_LINK_NAME:-Qwen3.6-27B-Q4_K_M.gguf}"

usage() {
  cat <<'EOF'
Usage:
  ./download_qwen36_27b.sh [--repo REPO] [--file FILE] [--target-dir DIR] [--link-name NAME] [--dry-run]

Defaults:
  REPO      bartowski/Qwen_Qwen3.6-27B-GGUF
  FILE      Qwen_Qwen3.6-27B-Q4_K_M.gguf
  DIR       ./models
  LINK_NAME Qwen3.6-27B-Q4_K_M.gguf

Env:
  HF_TOKEN  optional Hugging Face token for gated/rate-limited downloads.
EOF
}

DRY_RUN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      MODEL_REPO="$2"
      shift 2
      ;;
    --file)
      MODEL_FILE="$2"
      shift 2
      ;;
    --target-dir)
      TARGET_DIR="$2"
      shift 2
      ;;
    --link-name)
      CANONICAL_LINK_NAME="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unbekanntes Argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

mkdir -p "$TARGET_DIR"

TARGET_PATH="$TARGET_DIR/$MODEL_FILE"
CANONICAL_PATH="$TARGET_DIR/$CANONICAL_LINK_NAME"

echo "Repo:   $MODEL_REPO"
echo "Datei:  $MODEL_FILE"
echo "Ziel:   $TARGET_PATH"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "Dry-run aktiv, kein Download."
  exit 0
fi

if [[ -s "$TARGET_PATH" ]]; then
  echo "Schon vorhanden: $TARGET_PATH"
else
  MODEL_API_URL="https://huggingface.co/api/models/$MODEL_REPO"
  if ! curl -fsSL "$MODEL_API_URL" | grep -Fq "\"rfilename\":\"$MODEL_FILE\""; then
    echo "Fehler: Datei nicht im Repo gefunden: $MODEL_FILE" >&2
    echo "Pruefe z. B. mit: curl -fsSL $MODEL_API_URL" >&2
    exit 1
  fi

  URL="https://huggingface.co/$MODEL_REPO/resolve/main/$MODEL_FILE?download=true"
  DOWNLOADED=0

  if command -v hf >/dev/null 2>&1; then
    echo "Download via: hf download"
    if hf download "$MODEL_REPO" "$MODEL_FILE" --local-dir "$TARGET_DIR" --local-dir-use-symlinks False; then
      DOWNLOADED=1
    else
      echo "Warnung: hf download fehlgeschlagen, versuche naechsten Downloader." >&2
    fi
  fi

  if [[ "$DOWNLOADED" -eq 0 ]] && command -v huggingface-cli >/dev/null 2>&1; then
    echo "Download via: huggingface-cli download"
    if huggingface-cli download "$MODEL_REPO" "$MODEL_FILE" --local-dir "$TARGET_DIR" --local-dir-use-symlinks False; then
      DOWNLOADED=1
    else
      echo "Warnung: huggingface-cli fehlgeschlagen, versuche naechsten Downloader." >&2
    fi
  fi

  if [[ "$DOWNLOADED" -eq 0 ]] && command -v wget >/dev/null 2>&1; then
    echo "Download via: wget -c"
    if [[ -n "${HF_TOKEN:-}" ]]; then
      if wget -c --header="Authorization: Bearer $HF_TOKEN" -O "$TARGET_PATH" "$URL"; then
        DOWNLOADED=1
      fi
    else
      if wget -c -O "$TARGET_PATH" "$URL"; then
        DOWNLOADED=1
      fi
    fi
  fi

  if [[ "$DOWNLOADED" -eq 0 ]] && command -v curl >/dev/null 2>&1; then
    echo "Download via: curl -L -C -"
    if [[ -n "${HF_TOKEN:-}" ]]; then
      if curl -fL --retry 4 -C - -H "Authorization: Bearer $HF_TOKEN" -o "$TARGET_PATH" "$URL"; then
        DOWNLOADED=1
      fi
    else
      if curl -fL --retry 4 -C - -o "$TARGET_PATH" "$URL"; then
        DOWNLOADED=1
      fi
    fi
  fi

  if [[ "$DOWNLOADED" -eq 0 ]]; then
    echo "Fehler: Download fehlgeschlagen (hf/huggingface-cli/wget/curl)." >&2
    exit 1
  fi
fi

if [[ ! -s "$TARGET_PATH" ]]; then
  echo "Fehler: Download unvollstaendig oder leer: $TARGET_PATH" >&2
  exit 1
fi

if [[ "$TARGET_PATH" != "$CANONICAL_PATH" ]]; then
  ln -sfn "$MODEL_FILE" "$CANONICAL_PATH"
  echo "Link gesetzt: $CANONICAL_PATH -> $MODEL_FILE"
fi

echo "Fertig."
echo "Starten mit:"
echo "  ./chat.sh"
